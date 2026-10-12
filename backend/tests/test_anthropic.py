import json

import anthropic
import httpx2
import pytest

import app.providers.anthropic as anthropic_module
from app.providers.anthropic import AnthropicProvider, split_system
from app.providers.base import ProviderError, RefusalError
from app.schemas import ChatMessage, ChatParams


class FakeAnthropic:
    """Answers the Anthropic API with canned responses and records requests."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.models = [
            {"id": "claude-opus-5-5", "max_tokens": 128000},
            {"id": "claude-haiku-4-5", "max_tokens": 64000},
            {"id": "claude-3-haiku", "max_tokens": 4096},
        ]
        self.stream_events: list[dict] = []
        self.status = 200
        self.error: dict | None = None

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx2.Response(self.status, json={"type": "error", "error": self.error})
        path = request.url.path
        if path == "/v1/models":
            data = [
                {
                    "type": "model",
                    "id": m["id"],
                    "display_name": m["id"],
                    "created_at": "2026-01-01T00:00:00Z",
                    "max_tokens": m["max_tokens"],
                }
                for m in self.models
            ]
            return httpx2.Response(
                200, json={"data": data, "has_more": False, "first_id": None, "last_id": None}
            )
        if path.startswith("/v1/models/"):
            mid = path.rsplit("/", 1)[1]
            m = next((m for m in self.models if m["id"] == mid), None)
            if m is None:
                return httpx2.Response(
                    404,
                    json={"type": "error", "error": {"type": "not_found_error", "message": "nope"}},
                )
            return httpx2.Response(
                200,
                json={
                    "type": "model",
                    "id": mid,
                    "display_name": mid,
                    "created_at": "2026-01-01T00:00:00Z",
                    "max_tokens": m["max_tokens"],
                },
            )
        if path == "/v1/messages":
            body = "".join(
                f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in self.stream_events
            )
            return httpx2.Response(
                200, content=body.encode(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(404)

    def body(self, i: int = -1) -> dict:
        return json.loads(self.requests[i].content)


def sse_reply(
    *texts: str,
    model="claude-opus-5-5",
    stop_reason="end_turn",
    stop_details=None,
    fallback_to: str | None = None,
) -> list[dict]:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 3,
                    "cache_creation_input_tokens": 0,
                },
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ]
    events += [
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}}
        for t in texts
    ]
    events.append({"type": "content_block_stop", "index": 0})
    delta = {"stop_reason": stop_reason, "stop_sequence": None}
    if stop_details:
        delta["stop_details"] = stop_details
    events.append({"type": "message_delta", "delta": delta, "usage": {"output_tokens": 7}})
    events.append({"type": "message_stop"})
    return events


@pytest.fixture
def fake(monkeypatch) -> FakeAnthropic:
    fake = FakeAnthropic()

    def make_client(api_key, base_url):
        return anthropic.AsyncAnthropic(
            api_key=api_key or "",
            base_url=base_url,
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(
                transport=httpx2.MockTransport(fake.handler)
            ),
        )

    monkeypatch.setattr(anthropic_module, "make_client", make_client)
    return fake


@pytest.fixture
def provider(fake, http) -> AnthropicProvider:
    return AnthropicProvider(
        id="anthropic",
        name="Anthropic",
        base_url="https://api.anthropic.com",
        client=http,
        api_key="sk-ant-test",
    )


async def collect(provider, model="claude-opus-5-5", messages=None, params=None):
    messages = messages or [ChatMessage(role="user", content="Hi")]
    return [c async for c in provider.stream_chat(model, messages, params or ChatParams())]


def test_split_system() -> None:
    system, rest = split_system(
        [ChatMessage(role="system", content="Be brief."), ChatMessage(role="user", content="Hi")]
    )
    assert system == "Be brief." and rest == [{"role": "user", "content": "Hi"}]
    assert split_system([ChatMessage(role="user", content="Hi")])[0] is None


async def test_list_models_sends_key_and_version(provider, fake) -> None:
    models = await provider.list_models()
    assert [m.id for m in models] == [
        "anthropic:claude-3-haiku",
        "anthropic:claude-haiku-4-5",
        "anthropic:claude-opus-5-5",
    ]
    assert models[0].provider_kind == "anthropic"
    headers = fake.requests[0].headers
    assert headers["x-api-key"] == "sk-ant-test" and "anthropic-version" in headers


async def test_stream_text_and_usage(provider, fake) -> None:
    fake.stream_events = sse_reply("Hel", "lo")
    chunks = await collect(
        provider,
        messages=[
            ChatMessage(role="system", content="Be brief."),
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content="Hey"),
            ChatMessage(role="user", content="Again"),
        ],
        params=ChatParams(temperature=0.2),
    )
    assert "".join(c.delta for c in chunks) == "Hello"
    done = chunks[-1]
    assert done.done and done.served_by is None
    assert done.usage == {
        "prompt_tokens": 15,
        "completion_tokens": 7,
        "total_tokens": 22,
        "cache_read_tokens": 3,
    }

    sent = fake.body()
    assert sent["system"] == "Be brief."
    assert sent["messages"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hey"},
        {"role": "user", "content": "Again"},
    ]
    assert sent["stream"] is True and sent["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in sent  # current models reject sampling params


async def test_fallback_opt_in_for_supported_models_on_claude_api(provider, fake) -> None:
    fake.stream_events = sse_reply("ok")
    await collect(provider, model="claude-opus-5-5")
    req = fake.requests[-1]
    assert fake.body()["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]

    fake.stream_events = sse_reply("ok", model="claude-haiku-4-5")
    await collect(provider, model="claude-haiku-4-5")
    assert "fallbacks" not in fake.body()
    assert "anthropic-beta" not in fake.requests[-1].headers


async def test_no_fallback_on_other_endpoints(fake, http) -> None:
    proxy = AnthropicProvider(
        id="p", name="Proxy", base_url="https://claude-proxy.example", client=http, api_key="k"
    )
    fake.stream_events = sse_reply("ok")
    await collect(proxy)
    assert "fallbacks" not in fake.body()


async def test_served_by_reported_when_fallback_answers(provider, fake) -> None:
    fake.stream_events = sse_reply("Answer", model="claude-opus-4-8")
    chunks = await collect(provider, model="claude-opus-5-5")
    assert chunks[-1].served_by == "claude-opus-4-8"


async def test_refusal_raises_refusal_error(provider, fake) -> None:
    fake.stream_events = sse_reply(
        "Partial",
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": "cyber", "explanation": None},
    )
    received = []
    with pytest.raises(RefusalError, match=r"declined.*cyber"):
        async for c in provider.stream_chat(
            "claude-opus-5-5", [ChatMessage(role="user", content="x")], ChatParams()
        ):
            received.append(c.delta)
    assert received == ["Partial"]


async def test_max_tokens_capped_by_model_limit(provider, fake) -> None:
    await provider.list_models()
    fake.stream_events = sse_reply("ok", model="claude-3-haiku")
    await collect(provider, model="claude-3-haiku")
    assert fake.body()["max_tokens"] == 4096
    fake.stream_events = sse_reply("ok")
    await collect(provider, model="claude-opus-5-5")
    assert fake.body()["max_tokens"] == 64000
    await collect(provider, model="claude-opus-5-5", params=ChatParams(max_tokens=500))
    assert fake.body()["max_tokens"] == 500


async def test_max_tokens_looked_up_when_not_listed_yet(provider, fake) -> None:
    fake.stream_events = sse_reply("ok", model="claude-3-haiku")
    await collect(provider, model="claude-3-haiku")
    assert fake.requests[0].url.path == "/v1/models/claude-3-haiku"
    assert fake.body()["max_tokens"] == 4096


@pytest.mark.parametrize(
    ("status", "error_type", "message"),
    [
        (401, "authentication_error", "Invalid Anthropic API key"),
        (403, "permission_error", "isn't allowed"),
        (404, "not_found_error", "Model not found"),
        (429, "rate_limit_error", "rate limit"),
        (529, "overloaded_error", "overloaded right now"),
        (500, "api_error", r"Anthropic API error \(500\): details$"),
    ],
)
async def test_errors_are_readable(provider, fake, status, error_type, message) -> None:
    fake.status = status
    fake.error = {"type": error_type, "message": "details"}
    with pytest.raises(ProviderError, match=message):
        await provider.list_models()
    with pytest.raises(ProviderError, match=message):
        await collect(provider)
    health = await provider.health()
    assert not health.ok and health.error


async def test_connection_error(monkeypatch, http) -> None:
    def failing(request):
        raise httpx2.ConnectError("refused", request=request)

    monkeypatch.setattr(
        anthropic_module,
        "make_client",
        lambda key, url: anthropic.AsyncAnthropic(
            api_key="k",
            base_url=url,
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(failing)),
        ),
    )
    p = AnthropicProvider(id="a", name="A", base_url="", client=http, api_key="k")
    assert p.base_url == "https://api.anthropic.com"
    with pytest.raises(ProviderError, match="Cannot connect to Anthropic"):
        await p.list_models()

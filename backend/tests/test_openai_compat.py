import json

import httpx
import pytest
import respx

from app.providers.base import ProviderError
from app.providers.openai_compat import DONE, OpenAICompatProvider, parse_sse_line
from app.schemas import ChatMessage, ChatParams

BASE = "https://api.example.test/v1"


def sse(*events: dict | str) -> bytes:
    out = []
    for e in events:
        out.append(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n")
    return "".join(out).encode()


def delta(text: str) -> dict:
    return {"choices": [{"index": 0, "delta": {"content": text}}]}


@pytest.fixture
def provider(http) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        id="groq", name="Groq", base_url=BASE, client=http, api_key="sk-test"
    )


# --- parser ---------------------------------------------------------------


def test_parse_delta() -> None:
    chunk = parse_sse_line(f"data: {json.dumps(delta('Hi'))}")
    assert chunk.delta == "Hi"


def test_parse_done_marker() -> None:
    assert parse_sse_line("data: [DONE]") is DONE


@pytest.mark.parametrize(
    "line",
    [
        "",
        ": keep-alive",
        "event: ping",
        'data: {"choices": [{"delta": {"role": "assistant"}}]}',
        'data: {"choices": [{"delta": {"content": null}}]}',
    ],
)
def test_parse_lines_without_content(line: str) -> None:
    assert parse_sse_line(line) is None


def test_parse_usage_only_event() -> None:
    chunk = parse_sse_line('data: {"choices": [], "usage": {"total_tokens": 9}}')
    assert chunk.delta == "" and chunk.usage == {"total_tokens": 9}


def test_parse_error_event() -> None:
    with pytest.raises(ProviderError, match="rate limited"):
        parse_sse_line('data: {"error": {"message": "rate limited"}}')


# --- HTTP -----------------------------------------------------------------


@respx.mock
async def test_list_models_sends_bearer(provider: OpenAICompatProvider) -> None:
    route = respx.get(f"{BASE}/models").respond(
        json={"object": "list", "data": [{"id": "llama-3.1-8b"}, {"id": "gemma2-9b"}]}
    )
    models = await provider.list_models()
    assert [m.id for m in models] == ["groq:gemma2-9b", "groq:llama-3.1-8b"]
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-test"


@respx.mock
async def test_no_auth_header_without_key(http) -> None:
    provider = OpenAICompatProvider(id="lm", name="LM Studio", base_url=BASE, client=http)
    route = respx.get(f"{BASE}/models").respond(json={"data": []})
    await provider.list_models()
    assert "authorization" not in route.calls.last.request.headers


@respx.mock
async def test_list_models_unauthorized(provider: OpenAICompatProvider) -> None:
    respx.get(f"{BASE}/models").respond(401, json={"error": {"message": "Invalid API Key"}})
    with pytest.raises(ProviderError, match="HTTP 401: Invalid API Key"):
        await provider.list_models()
    health = await provider.health()
    assert not health.ok and "Invalid API Key" in health.error


@respx.mock
async def test_list_models_timeout(provider: OpenAICompatProvider) -> None:
    respx.get(f"{BASE}/models").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError, match="Timed out"):
        await provider.list_models()


@respx.mock
async def test_stream_chat(provider: OpenAICompatProvider) -> None:
    route = respx.post(f"{BASE}/chat/completions").respond(
        content=sse(
            {"choices": [{"delta": {"role": "assistant"}}]},
            delta("Hel"),
            delta("lo"),
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
            "[DONE]",
        ),
        headers={"content-type": "text/event-stream"},
    )
    chunks = [
        c
        async for c in provider.stream_chat(
            "llama-3.1-8b", [ChatMessage(role="user", content="hi")], ChatParams(max_tokens=10)
        )
    ]
    assert [c.delta for c in chunks[:-1]] == ["Hel", "lo"]
    assert chunks[-1].done and chunks[-1].usage == {"prompt_tokens": 3, "completion_tokens": 2}

    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer sk-test"
    sent = json.loads(request.content)
    assert sent["stream"] is True and sent["max_tokens"] == 10
    assert "temperature" not in sent


@respx.mock
async def test_stream_chat_without_done_marker(provider: OpenAICompatProvider) -> None:
    respx.post(f"{BASE}/chat/completions").respond(content=sse(delta("ok")))
    chunks = [c async for c in provider.stream_chat("m", [], ChatParams())]
    assert chunks[0].delta == "ok" and chunks[-1].done and chunks[-1].usage is None


@respx.mock
async def test_stream_chat_mid_stream_error(provider: OpenAICompatProvider) -> None:
    respx.post(f"{BASE}/chat/completions").respond(
        content=sse(delta("par"), {"error": {"message": "context length exceeded"}})
    )
    received = []
    with pytest.raises(ProviderError, match="context length exceeded"):
        async for c in provider.stream_chat("m", [], ChatParams()):
            received.append(c.delta)
    assert received == ["par"]


@respx.mock
async def test_stream_chat_http_error(provider: OpenAICompatProvider) -> None:
    respx.post(f"{BASE}/chat/completions").respond(500, text="upstream exploded")
    with pytest.raises(ProviderError, match="HTTP 500: upstream exploded"):
        async for _ in provider.stream_chat("m", [], ChatParams()):
            pass


@respx.mock
async def test_list_models_hides_non_chat_models(provider: OpenAICompatProvider) -> None:
    ids = [
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "whisper-large-v3",
        "canopylabs/orpheus-v1-english",
        "meta-llama/llama-prompt-guard-2-22m",
        "openai/gpt-oss-safeguard-20b",
        "text-embedding-3-small",
        "tts-1",
        "dall-e-3",
        "omni-moderation-latest",
    ]
    respx.get(f"{BASE}/models").respond(json={"data": [{"id": i} for i in ids]})
    models = await provider.list_models()
    assert [m.name for m in models] == ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

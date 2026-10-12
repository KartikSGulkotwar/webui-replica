import json

import pytest
import respx

from app.models import Provider
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from app.routers.chat import make_title, stream_and_persist
from app.schemas import ChatMessage, ChatParams, StreamChunk

OLLAMA = "http://ollama.test"
GROQ = "https://groq.test/v1"


@pytest.fixture
def providers(session, cipher) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.add(
        Provider(
            id="groq",
            name="Groq",
            kind="openai_compat",
            base_url=GROQ,
            api_key_encrypted=cipher.encrypt("gsk"),
        )
    )
    session.add(Provider(id="off", name="Off", kind="ollama", base_url="http://x", enabled=False))
    session.commit()


@pytest.fixture
def conv(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


def ollama_reply(*parts: str) -> bytes:
    lines = [{"message": {"content": p}, "done": False} for p in parts]
    lines.append({"message": {"content": ""}, "done": True, "eval_count": len(parts)})
    return b"".join(json.dumps(line).encode() + b"\n" for line in lines)


def groq_reply(*parts: str) -> bytes:
    events = [{"choices": [{"delta": {"content": p}}]} for p in parts]
    events.append({"choices": [], "usage": {"total_tokens": 5}})
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return body.encode()


def events(resp) -> list[dict]:
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def chat(client, conv: str, model_id: str, message: str):
    return client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": model_id, "message": message},
    )


# --- titles -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("Hello there", "Hello there"),
        ("  How do I\nreverse a list in Python quickly?", "How do I reverse a list…"),
        ("x" * 80, "x" * 60 + "…"),
        ("   ", "New chat"),
    ],
)
def test_make_title(text: str, title: str) -> None:
    assert make_title(text) == title


# --- streaming endpoint -------------------------------------------------------


@respx.mock
def test_stream_normalizes_ollama_and_persists(client, providers, conv) -> None:
    respx.post(f"{OLLAMA}/api/chat").respond(content=ollama_reply("Hel", "lo"))

    resp = chat(client, conv, "ollama:qwen2.5:0.5b", "Say hello to me please friend")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    evts = events(resp)
    assert evts[:2] == [{"delta": "Hel"}, {"delta": "lo"}]
    assert evts[-1]["done"] is True and evts[-1]["usage"]["completion_tokens"] == 2
    assert isinstance(evts[-1]["message_id"], int)

    detail = client.get(f"/api/conversations/{conv}").json()
    assert detail["title"] == "Say hello to me please friend"
    assert [(m["role"], m["content"], m["model_id"]) for m in detail["messages"]] == [
        ("user", "Say hello to me please friend", None),
        ("assistant", "Hello", "ollama:qwen2.5:0.5b"),
    ]


@respx.mock
def test_switch_provider_mid_conversation(client, providers, conv) -> None:
    respx.post(f"{OLLAMA}/api/chat").respond(content=ollama_reply("Paris."))
    groq_route = respx.post(f"{GROQ}/chat/completions").respond(content=groq_reply("About 2.1M."))

    chat(client, conv, "ollama:llama3.2:1b", "Capital of France?")
    second = events(chat(client, conv, "groq:llama-3.1-8b", "Population?"))

    assert second[0] == {"delta": "About 2.1M."}
    assert second[-1]["done"] is True and second[-1]["usage"] == {"total_tokens": 5}

    # The second provider receives the whole history, including the first model's answer.
    sent = json.loads(groq_route.calls.last.request.content)
    assert sent["model"] == "llama-3.1-8b"
    assert sent["messages"] == [
        {"role": "user", "content": "Capital of France?"},
        {"role": "assistant", "content": "Paris."},
        {"role": "user", "content": "Population?"},
    ]

    messages = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert [m["model_id"] for m in messages if m["role"] == "assistant"] == [
        "ollama:llama3.2:1b",
        "groq:llama-3.1-8b",
    ]


@respx.mock
def test_title_only_set_from_first_message(client, providers, conv) -> None:
    respx.post(f"{OLLAMA}/api/chat").respond(content=ollama_reply("ok"))
    chat(client, conv, "ollama:m", "First question")
    chat(client, conv, "ollama:m", "Second question")
    assert client.get(f"/api/conversations/{conv}").json()["title"] == "First question"


@respx.mock
def test_custom_title_is_not_overwritten(client, providers) -> None:
    conv = client.post("/api/conversations", json={"title": "Mine"}).json()["id"]
    respx.post(f"{OLLAMA}/api/chat").respond(content=ollama_reply("ok"))
    chat(client, conv, "ollama:m", "Hello")
    assert client.get(f"/api/conversations/{conv}").json()["title"] == "Mine"


@respx.mock
def test_provider_error_becomes_sse_error(client, providers, conv) -> None:
    respx.post(f"{GROQ}/chat/completions").respond(401, json={"error": {"message": "Bad key"}})

    resp = chat(client, conv, "groq:m", "hi")

    assert resp.status_code == 200
    assert events(resp) == [{"error": "HTTP 401: Bad key"}]
    messages = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert [m["role"] for m in messages] == ["user"]  # nothing produced, nothing saved


@respx.mock
def test_partial_reply_saved_on_mid_stream_error(client, providers, conv) -> None:
    body = (
        'data: {"choices": [{"delta": {"content": "Partial"}}]}\n\n'
        'data: {"error": {"message": "overloaded"}}\n\n'
    )
    respx.post(f"{GROQ}/chat/completions").respond(content=body.encode())

    evts = events(chat(client, conv, "groq:m", "hi"))

    assert evts == [{"delta": "Partial"}, {"error": "overloaded"}]
    messages = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert messages[-1]["role"] == "assistant" and messages[-1]["content"] == "Partial"


@pytest.mark.parametrize(
    ("model_id", "status", "detail"),
    [
        ("nocolon", 422, "Invalid model id"),
        ("unknown:m", 400, "not found or disabled"),
        ("off:m", 400, "not found or disabled"),
    ],
)
def test_rejects_bad_model(client, providers, conv, model_id, status, detail) -> None:
    resp = chat(client, conv, model_id, "hi")
    assert resp.status_code == status and detail in resp.json()["detail"]
    # Validation happens before the user message is stored.
    assert client.get(f"/api/conversations/{conv}").json()["messages"] == []


def test_unknown_conversation(client, providers) -> None:
    assert chat(client, "nope", "ollama:m", "hi").status_code == 404


def test_empty_message_rejected(client, providers, conv) -> None:
    assert chat(client, conv, "ollama:m", "").status_code == 422


# --- stop / disconnect --------------------------------------------------------


class FakeProvider(OllamaProvider):
    def __init__(self, chunks: list[StreamChunk], fail: Exception | None = None) -> None:
        self._chunks = chunks
        self._fail = fail

    async def stream_chat(self, model, messages, params, tools=None):
        for chunk in self._chunks:
            yield chunk
        if self._fail:
            raise self._fail


async def test_partial_reply_saved_when_client_stops(app, client, conv) -> None:
    provider = FakeProvider(
        [StreamChunk(delta="One "), StreamChunk(delta="two "), StreamChunk(delta="three")]
    )
    gen = stream_and_persist(
        app.state.engine,
        provider,
        conv,
        "ollama:m",
        "m",
        [ChatMessage(role="user", content="count")],
        ChatParams(),
    )

    assert await gen.__anext__() == 'data: {"delta": "One "}\n\n'
    assert await gen.__anext__() == 'data: {"delta": "two "}\n\n'
    await gen.aclose()  # what Starlette does when the browser aborts the request

    messages = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [("assistant", "One two ")]


async def test_nothing_saved_when_stopped_before_first_token(app, client, conv) -> None:
    provider = FakeProvider([StreamChunk(delta="never seen")])
    gen = stream_and_persist(app.state.engine, provider, conv, "ollama:m", "m", [], ChatParams())
    await gen.aclose()
    assert client.get(f"/api/conversations/{conv}").json()["messages"] == []


async def test_unexpected_exception_gives_generic_error(app, client, conv) -> None:
    provider = FakeProvider([StreamChunk(delta="a")], fail=RuntimeError("secret internals"))
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine, provider, conv, "ollama:m", "m", [], ChatParams()
        )
    ]
    assert out[-1] == 'data: {"error": "Internal error while streaming the response"}\n\n'
    assert "secret" not in "".join(out)


async def test_provider_error_class_is_reported(app, conv) -> None:
    provider = FakeProvider([], fail=ProviderError("model not loaded"))
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine, provider, conv, "ollama:m", "m", [], ChatParams()
        )
    ]
    assert out == ['data: {"error": "model not loaded"}\n\n']


# --- refusals and fallbacks ------------------------------------------------------


class ServedByProvider(OllamaProvider):
    id = "anthropic"

    def __init__(self, chunks):
        self._chunks = chunks

    async def stream_chat(self, model, messages, params, tools=None):
        for c in self._chunks:
            yield c


async def test_reply_saved_under_the_model_that_answered(app, client, conv) -> None:
    provider = ServedByProvider(
        [StreamChunk(delta="Hi"), StreamChunk(done=True, served_by="claude-opus-4-8")]
    )
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine,
            provider,
            conv,
            "anthropic:claude-opus-5-5",
            "claude-opus-5-5",
            [],
            ChatParams(),
        )
    ]
    done = json.loads(out[-1][6:])
    assert done["model_id"] == "anthropic:claude-opus-4-8"
    saved = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert saved[-1]["model_id"] == "anthropic:claude-opus-4-8"


async def test_refusal_discards_partial_reply(app, client, conv) -> None:
    from app.providers.base import RefusalError

    provider = FakeProvider(
        [StreamChunk(delta="Half an ans")], fail=RefusalError("Claude declined")
    )
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine, provider, conv, "a:m", "m", [], ChatParams()
        )
    ]
    assert json.loads(out[-1][6:]) == {"error": "Claude declined", "discard": True}
    assert client.get(f"/api/conversations/{conv}").json()["messages"] == []

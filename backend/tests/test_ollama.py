import json

import httpx
import pytest
import respx

from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider, parse_ollama_line
from app.schemas import ChatMessage, ChatParams

BASE = "http://ollama.test:11434"


def ndjson(*objs: dict) -> bytes:
    return b"".join(json.dumps(o).encode() + b"\n" for o in objs)


@pytest.fixture
def provider(http) -> OllamaProvider:
    return OllamaProvider(id="ollama", name="Ollama", base_url=BASE + "/", client=http)


# --- parser ---------------------------------------------------------------


def test_parse_content_line() -> None:
    chunk = parse_ollama_line('{"message": {"role": "assistant", "content": "Hi"}, "done": false}')
    assert chunk is not None and chunk.delta == "Hi" and not chunk.done


def test_parse_blank_and_empty_content_lines() -> None:
    assert parse_ollama_line("") is None
    assert parse_ollama_line('{"message": {"content": ""}, "done": false}') is None


def test_parse_done_line_with_usage() -> None:
    chunk = parse_ollama_line('{"done": true, "prompt_eval_count": 7, "eval_count": 5}')
    assert chunk is not None and chunk.done
    assert chunk.usage == {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}


def test_parse_error_line() -> None:
    with pytest.raises(ProviderError, match="model 'x' not found"):
        parse_ollama_line('{"error": "model \'x\' not found"}')


def test_parse_malformed_line() -> None:
    with pytest.raises(ProviderError, match="Malformed"):
        parse_ollama_line("{not json")


# --- HTTP -----------------------------------------------------------------


@respx.mock
async def test_list_models_namespaced(provider: OllamaProvider) -> None:
    respx.get(f"{BASE}/api/tags").respond(
        json={"models": [{"name": "mistral:7b"}, {"name": "llama3.2:1b"}]}
    )
    models = await provider.list_models()
    assert [m.id for m in models] == ["ollama:llama3.2:1b", "ollama:mistral:7b"]
    assert models[0].name == "llama3.2:1b"
    assert models[0].provider_kind == "ollama"


@respx.mock
async def test_health_ok(provider: OllamaProvider) -> None:
    respx.get(f"{BASE}/api/tags").respond(json={"models": [{"name": "a"}]})
    health = await provider.health()
    assert health.ok and health.model_count == 1 and health.latency_ms is not None


@respx.mock
async def test_health_connection_refused(provider: OllamaProvider) -> None:
    respx.get(f"{BASE}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    health = await provider.health()
    assert not health.ok
    assert health.error == f"Cannot connect to {BASE}"


@respx.mock
async def test_stream_chat(provider: OllamaProvider) -> None:
    route = respx.post(f"{BASE}/api/chat").respond(
        content=ndjson(
            {"message": {"role": "assistant", "content": "Hel"}, "done": False},
            {"message": {"role": "assistant", "content": "lo"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 2},
        )
    )
    chunks = [
        c
        async for c in provider.stream_chat(
            "llama3.2:1b",
            [ChatMessage(role="user", content="hi")],
            ChatParams(temperature=0.2, max_tokens=50),
        )
    ]
    assert "".join(c.delta for c in chunks) == "Hello"
    assert chunks[-1].done and chunks[-1].usage == {"completion_tokens": 2, "total_tokens": 2}

    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "llama3.2:1b"
    assert sent["stream"] is True
    assert sent["options"] == {"temperature": 0.2, "num_predict": 50}


@respx.mock
async def test_stream_chat_http_error(provider: OllamaProvider) -> None:
    respx.post(f"{BASE}/api/chat").respond(404, json={"error": "model 'nope' not found"})
    with pytest.raises(ProviderError, match="HTTP 404: model 'nope' not found"):
        async for _ in provider.stream_chat("nope", [], ChatParams()):
            pass


@respx.mock
async def test_stream_chat_truncated(provider: OllamaProvider) -> None:
    respx.post(f"{BASE}/api/chat").respond(
        content=ndjson({"message": {"content": "partial"}, "done": False})
    )
    with pytest.raises(ProviderError, match="ended unexpectedly"):
        async for _ in provider.stream_chat("m", [], ChatParams()):
            pass

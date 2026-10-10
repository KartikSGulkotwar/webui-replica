import httpx
import respx

from app.models import Provider


def seed(session, cipher) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url="http://ollama.test"))
    session.add(
        Provider(
            id="groq",
            name="Groq",
            kind="openai_compat",
            base_url="https://groq.test/v1",
            api_key_encrypted=cipher.encrypt("gsk"),
        )
    )
    session.add(
        Provider(id="off", name="Off", kind="ollama", base_url="http://off.test", enabled=False)
    )
    session.commit()


@respx.mock
def test_models_merges_providers(client, session, cipher) -> None:
    seed(session, cipher)
    respx.get("http://ollama.test/api/tags").respond(json={"models": [{"name": "llama3.2:1b"}]})
    respx.get("https://groq.test/v1/models").respond(json={"data": [{"id": "llama-3.1-8b"}]})

    body = client.get("/api/models").json()

    assert [m["id"] for m in body["models"]] == ["groq:llama-3.1-8b", "ollama:llama3.2:1b"]
    assert body["providers"] == [
        {"id": "groq", "name": "Groq", "kind": "openai_compat", "ok": True, "error": None},
        {"id": "ollama", "name": "Ollama", "kind": "ollama", "ok": True, "error": None},
    ]


@respx.mock
def test_models_tolerates_failing_provider(client, session, cipher) -> None:
    seed(session, cipher)
    respx.get("http://ollama.test/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    respx.get("https://groq.test/v1/models").respond(json={"data": [{"id": "llama-3.1-8b"}]})

    resp = client.get("/api/models")

    assert resp.status_code == 200
    body = resp.json()
    assert [m["id"] for m in body["models"]] == ["groq:llama-3.1-8b"]
    ollama = next(p for p in body["providers"] if p["id"] == "ollama")
    assert ollama["ok"] is False
    assert ollama["error"] == "Cannot connect to http://ollama.test"


def test_models_with_no_providers(client) -> None:
    assert client.get("/api/models").json() == {"models": [], "providers": []}


@respx.mock
def test_api_key_never_returned(client, session, cipher) -> None:
    seed(session, cipher)
    respx.get("http://ollama.test/api/tags").respond(json={"models": []})
    respx.get("https://groq.test/v1/models").respond(json={"data": []})
    text = client.get("/api/models").text
    assert "gsk" not in text and "api_key" not in text

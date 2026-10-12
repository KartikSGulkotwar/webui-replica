import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.main import create_app
from app.models import Provider
from tests.conftest import signup

GROQ = "https://api.groq.test/openai/v1"


def create(client, **overrides) -> dict:
    body = {"name": "Groq", "kind": "openai_compat", "base_url": GROQ, "api_key": "gsk-123"}
    body.update(overrides)
    resp = client.post("/api/providers", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_encrypts_key_and_never_returns_it(client, session, cipher) -> None:
    created = create(client, base_url=GROQ + "/")

    assert created["id"] == "groq"
    assert created["has_key"] is True
    assert created["base_url"] == GROQ  # trailing slash stripped
    assert "api_key" not in created and "gsk-123" not in str(created)

    row = session.get(Provider, "groq")
    assert row.api_key_encrypted != "gsk-123"
    assert cipher.decrypt(row.api_key_encrypted) == "gsk-123"

    listed = client.get("/api/providers")
    assert "gsk-123" not in listed.text and "api_key_encrypted" not in listed.text


def test_create_generates_unique_ids(client) -> None:
    assert create(client)["id"] == "groq"
    assert create(client)["id"] == "groq-2"
    assert create(client, name="My Local LLM!", api_key=None)["id"] == "my-local-llm"


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"base_url": "ftp://x"}, "http:// or https://"),
        ({"base_url": "api.groq.com"}, "http:// or https://"),
        ({"name": "   "}, "blank"),
        ({"kind": "gemini"}, "kind"),
    ],
)
def test_create_validation(client, override, fragment) -> None:
    body = {"name": "X", "kind": "ollama", "base_url": "http://localhost:11434", **override}
    resp = client.post("/api/providers", json=body)
    assert resp.status_code == 422 and fragment in resp.text


def test_update_fields_and_key_semantics(client, session, cipher) -> None:
    create(client)

    # Omitted api_key keeps the stored key.
    resp = client.patch("/api/providers/groq", json={"name": "Groq Cloud", "enabled": False})
    body = resp.json()
    assert body["name"] == "Groq Cloud" and body["enabled"] is False and body["has_key"] is True

    # A new key replaces it.
    client.patch("/api/providers/groq", json={"api_key": "gsk-new"})
    session.expire_all()
    assert cipher.decrypt(session.get(Provider, "groq").api_key_encrypted) == "gsk-new"

    # Empty string removes it.
    assert client.patch("/api/providers/groq", json={"api_key": ""}).json()["has_key"] is False

    assert client.patch("/api/providers/nope", json={"enabled": True}).status_code == 404
    assert client.patch("/api/providers/groq", json={"base_url": "nope"}).status_code == 422


def test_delete(client) -> None:
    create(client)
    assert client.delete("/api/providers/groq").status_code == 204
    assert client.get("/api/providers").json() == []
    assert client.delete("/api/providers/groq").status_code == 404


@respx.mock
def test_disabled_and_deleted_providers_leave_model_list(client) -> None:
    create(client)
    respx.get(f"{GROQ}/models").respond(json={"data": [{"id": "llama"}]})
    assert [m["id"] for m in client.get("/api/models").json()["models"]] == ["groq:llama"]

    client.patch("/api/providers/groq", json={"enabled": False})
    assert client.get("/api/models").json()["models"] == []

    client.patch("/api/providers/groq", json={"enabled": True})
    client.delete("/api/providers/groq")
    assert client.get("/api/models").json() == {"models": [], "providers": []}


@respx.mock
def test_registry_picks_up_new_key(client) -> None:
    create(client)
    route = respx.get(f"{GROQ}/models").respond(json={"data": []})
    client.get("/api/models")
    assert route.calls.last.request.headers["authorization"] == "Bearer gsk-123"

    client.patch("/api/providers/groq", json={"api_key": "gsk-rotated"})
    client.get("/api/models")
    assert route.calls.last.request.headers["authorization"] == "Bearer gsk-rotated"


@respx.mock
def test_health_endpoint(client) -> None:
    create(client, enabled=False)  # disabled providers can still be checked
    respx.get(f"{GROQ}/models").respond(json={"data": [{"id": "a"}, {"id": "b"}]})
    body = client.get("/api/providers/groq/health").json()
    assert body["ok"] is True and body["model_count"] == 2

    respx.get(f"{GROQ}/models").respond(401, json={"error": {"message": "Invalid API Key"}})
    body = client.get("/api/providers/groq/health").json()
    assert body == {
        "ok": False,
        "latency_ms": None,
        "model_count": None,
        "error": "HTTP 401: Invalid API Key",
    }

    assert client.get("/api/providers/nope/health").status_code == 404


@respx.mock
def test_test_connection_with_form_values(client) -> None:
    route = respx.get("http://lmstudio.test/v1/models").respond(json={"data": [{"id": "x"}]})
    resp = client.post(
        "/api/providers/test",
        json={"kind": "openai_compat", "base_url": "http://lmstudio.test/v1", "api_key": "k"},
    )
    assert resp.json()["ok"] is True
    assert route.calls.last.request.headers["authorization"] == "Bearer k"


@respx.mock
def test_test_connection_reuses_stored_key_when_editing(client) -> None:
    create(client)
    route = respx.get(f"{GROQ}/models").respond(json={"data": []})
    client.post(
        "/api/providers/test",
        json={"kind": "openai_compat", "base_url": GROQ, "provider_id": "groq"},
    )
    assert route.calls.last.request.headers["authorization"] == "Bearer gsk-123"


@respx.mock
def test_test_connection_unreachable(client) -> None:
    respx.get("http://down.test:11434/api/tags").mock(side_effect=httpx.ConnectError("x"))
    body = client.post(
        "/api/providers/test", json={"kind": "ollama", "base_url": "http://down.test:11434"}
    ).json()
    assert body["ok"] is False and "Cannot connect" in body["error"]


def test_key_without_encryption_key_is_rejected(settings) -> None:
    settings.encryption_key = ""
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        signup(client, "admin@example.com")
        resp = client.post(
            "/api/providers",
            json={"name": "G", "kind": "openai_compat", "base_url": GROQ, "api_key": "k"},
        )
        assert resp.status_code == 400 and "ENCRYPTION_KEY" in resp.json()["detail"]
        # Keyless providers still work.
        ok = client.post(
            "/api/providers",
            json={"name": "O", "kind": "ollama", "base_url": "http://localhost:11434"},
        )
        assert ok.status_code == 201
        assert client.get("/api/config").json()["encryption_configured"] is False


def test_providers_are_admin_only(user_client, anon_client) -> None:
    body = {"name": "G", "kind": "ollama", "base_url": "http://x"}
    for c, expected in ((user_client, 403), (anon_client, 401)):
        assert c.get("/api/providers").status_code == expected
        assert c.post("/api/providers", json=body).status_code == expected
        assert c.patch("/api/providers/x", json={"enabled": False}).status_code == expected
        assert c.delete("/api/providers/x").status_code == expected
        assert c.get("/api/providers/x/health").status_code == expected
        test = c.post("/api/providers/test", json={"kind": "ollama", "base_url": "http://x"})
        assert test.status_code == expected

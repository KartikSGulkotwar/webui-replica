import json

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.main import create_app
from app.models import Conversation, Provider
from app.owner import COOKIE


@pytest.fixture
def isolated_app(settings):
    settings.isolate_chats_by_browser = True
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as session:
        session.add(Provider(id="o", name="O", kind="ollama", base_url="http://o.test"))
        session.commit()
    return app


def test_cookie_issued_on_first_write_not_on_reads(client) -> None:
    # Reads (a page load fires several at once) never issue an ID, so parallel
    # responses can't race to overwrite each other's cookie.
    assert "set-cookie" not in client.get("/api/health").headers
    assert "set-cookie" not in client.get("/api/conversations").headers

    resp = client.post("/api/conversations", json={})
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Max-Age=" in cookie
    assert "Secure" not in cookie  # plain http test server
    # Sent back automatically afterwards, so no new cookie is issued.
    assert "set-cookie" not in client.post("/api/conversations", json={}).headers


def test_cookie_is_secure_behind_https_proxy(client) -> None:
    resp = client.post("/api/conversations", json={}, headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in resp.headers["set-cookie"]


def test_invalid_cookie_is_replaced(client) -> None:
    client.cookies.set(COOKIE, "bad value!")
    resp = client.post("/api/conversations", json={})
    assert resp.headers["set-cookie"].startswith(f"{COOKIE}=")


def test_parallel_first_reads_do_not_change_the_owner(isolated_app) -> None:
    with TestClient(isolated_app) as client:
        for path in ("/api/models", "/api/config", "/api/conversations"):
            client.get(path)
        conv = client.post("/api/conversations", json={}).json()["id"]
        for path in ("/api/models", "/api/config", "/api/conversations"):
            client.get(path)
        assert [c["id"] for c in client.get("/api/conversations").json()] == [conv]


def test_conversation_records_owner(client, session) -> None:
    conv_id = client.post("/api/conversations", json={}).json()["id"]
    owner = client.cookies.get(COOKIE)
    assert session.get(Conversation, conv_id).owner_id == owner


def test_shared_mode_shows_everyone_everything(app) -> None:
    with TestClient(app) as alice, TestClient(app) as bob:
        conv = alice.post("/api/conversations", json={"title": "Alice"}).json()["id"]
        assert [c["id"] for c in bob.get("/api/conversations").json()] == [conv]
        assert bob.get(f"/api/conversations/{conv}").status_code == 200


@respx.mock
def test_isolated_mode_hides_other_browsers_chats(isolated_app) -> None:
    reply = json.dumps({"message": {"content": "ok"}, "done": True}).encode() + b"\n"
    respx.post("http://o.test/api/chat").respond(content=reply)

    with TestClient(isolated_app) as alice, TestClient(isolated_app) as bob:
        mine = alice.post("/api/conversations", json={"title": "Alice"}).json()["id"]
        bobs = bob.post("/api/conversations", json={"title": "Bob"}).json()["id"]

        assert [c["id"] for c in alice.get("/api/conversations").json()] == [mine]
        assert [c["id"] for c in bob.get("/api/conversations").json()] == [bobs]

        # Every way of touching Alice's chat looks like it doesn't exist to Bob.
        assert bob.get(f"/api/conversations/{mine}").status_code == 404
        assert bob.patch(f"/api/conversations/{mine}", json={"title": "x"}).status_code == 404
        assert bob.delete(f"/api/conversations/{mine}").status_code == 404
        stream = bob.post(
            "/api/chat/stream",
            json={"conversation_id": mine, "model_id": "o:m", "message": "hi"},
        )
        assert stream.status_code == 404

        # Alice still has full access.
        assert alice.get(f"/api/conversations/{mine}").json()["title"] == "Alice"
        ok = alice.post(
            "/api/chat/stream",
            json={"conversation_id": mine, "model_id": "o:m", "message": "hi"},
        )
        assert ok.status_code == 200 and "set-cookie" not in ok.headers
        assert len(alice.get(f"/api/conversations/{mine}").json()["messages"]) == 2


def test_isolated_mode_hides_legacy_unowned_chats(isolated_app) -> None:
    with Session(isolated_app.state.engine) as session:
        session.add(Conversation(id="legacy", title="Old"))
        session.commit()
    with TestClient(isolated_app) as client:
        assert client.get("/api/conversations").json() == []
        assert client.get("/api/conversations/legacy").status_code == 404


def test_config_exposes_default_model(settings) -> None:
    settings.default_model = "groq:openai/gpt-oss-120b"
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert client.get("/api/config").json()["default_model"] == "groq:openai/gpt-oss-120b"

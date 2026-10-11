import json

import pytest
import respx

from app.models import Provider

PROTECTED = [
    ("get", "/api/models"),
    ("get", "/api/conversations"),
    ("post", "/api/conversations"),
    ("get", "/api/conversations/x"),
    ("patch", "/api/conversations/x"),
    ("delete", "/api/conversations/x"),
    ("post", "/api/chat/stream"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_signed_out_requests_are_rejected(anon_client, method, path) -> None:
    kwargs = {"json": {}} if method in ("post", "patch") else {}
    assert getattr(anon_client, method)(path, **kwargs).status_code == 401


def test_public_endpoints(anon_client) -> None:
    assert anon_client.get("/api/health").status_code == 200
    assert anon_client.get("/api/config").status_code == 200


@respx.mock
def test_users_only_see_their_own_conversations(client, user_client, session) -> None:
    session.add(Provider(id="o", name="O", kind="ollama", base_url="http://o.test"))
    session.commit()
    reply = json.dumps({"message": {"content": "ok"}, "done": True}).encode() + b"\n"
    respx.post("http://o.test/api/chat").respond(content=reply)

    admins = client.post("/api/conversations", json={"title": "Admin's"}).json()["id"]
    users = user_client.post("/api/conversations", json={"title": "User's"}).json()["id"]

    assert [c["id"] for c in client.get("/api/conversations").json()] == [admins]
    assert [c["id"] for c in user_client.get("/api/conversations").json()] == [users]

    # Even an admin can't read another user's chats through the chat API.
    for c, other in ((user_client, admins), (client, users)):
        assert c.get(f"/api/conversations/{other}").status_code == 404
        assert c.patch(f"/api/conversations/{other}", json={"title": "x"}).status_code == 404
        assert c.delete(f"/api/conversations/{other}").status_code == 404
        stream = c.post(
            "/api/chat/stream",
            json={"conversation_id": other, "model_id": "o:m", "message": "hi"},
        )
        assert stream.status_code == 404

    ok = user_client.post(
        "/api/chat/stream", json={"conversation_id": users, "model_id": "o:m", "message": "hi"}
    )
    assert ok.status_code == 200
    assert len(user_client.get(f"/api/conversations/{users}").json()["messages"]) == 2


@respx.mock
def test_approved_user_can_list_models(user_client, session) -> None:
    session.add(Provider(id="o", name="O", kind="ollama", base_url="http://o.test"))
    session.commit()
    respx.get("http://o.test/api/tags").respond(json={"models": [{"name": "m"}]})
    assert [m["id"] for m in user_client.get("/api/models").json()["models"]] == ["o:m"]

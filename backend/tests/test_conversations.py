from sqlmodel import select

from app.models import Message


def create(client, **body) -> dict:
    resp = client.post("/api/conversations", json=body)
    assert resp.status_code == 201
    return resp.json()


def test_create_and_list(client) -> None:
    a = create(client)
    b = create(client, title="  Trip ideas ")
    assert a["title"] == "New chat"
    assert b["title"] == "Trip ideas"
    ids = [c["id"] for c in client.get("/api/conversations").json()]
    assert ids == [b["id"], a["id"]]  # most recently updated first


def test_get_with_messages(client) -> None:
    conv = create(client)
    body = client.get(f"/api/conversations/{conv['id']}").json()
    assert body["id"] == conv["id"] and body["messages"] == []


def test_get_missing(client) -> None:
    assert client.get("/api/conversations/nope").status_code == 404


def test_rename(client) -> None:
    conv = create(client)
    resp = client.patch(f"/api/conversations/{conv['id']}", json={"title": "Renamed"})
    assert resp.status_code == 200 and resp.json()["title"] == "Renamed"
    assert (
        client.patch(f"/api/conversations/{conv['id']}", json={"title": "   "}).status_code == 422
    )
    assert client.patch("/api/conversations/nope", json={"title": "x"}).status_code == 404


def test_delete_removes_messages(client, session) -> None:
    conv = create(client)
    session.add(Message(conversation_id=conv["id"], role="user", content="hi"))
    session.commit()

    assert client.delete(f"/api/conversations/{conv['id']}").status_code == 204
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 404
    assert session.exec(select(Message)).all() == []
    assert client.delete(f"/api/conversations/{conv['id']}").status_code == 404

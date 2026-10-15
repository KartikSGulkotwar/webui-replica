"""Notes: CRUD, search, privacy, AI helpers and "ask in chat"."""

import json

import pytest

import app.routers.notes as notes_router
from app.catalog import ResolvedModel
from app.schemas import StreamChunk
from tests.test_tool_calling import ScriptedProvider


def events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data:")]


@pytest.fixture
def fake_model(monkeypatch):
    provider = ScriptedProvider(
        [[StreamChunk(delta="Better "), StreamChunk(delta="text."), StreamChunk(done=True)]]
    )
    monkeypatch.setattr(
        notes_router, "pick_model", lambda *a: (provider, ResolvedModel("ollama", "m"))
    )
    return provider


def test_notes_crud_and_search(client) -> None:
    a = client.post("/api/notes", json={"title": " Groceries ", "content": "Milk, eggs"}).json()
    b = client.post("/api/notes", json={"title": "Ideas", "content": "# Big plan\nShip it"}).json()
    assert a["title"] == "Groceries"
    listed = client.get("/api/notes").json()
    assert [n["title"] for n in listed] == ["Ideas", "Groceries"]  # newest first
    assert listed[0]["snippet"].startswith("Big plan")

    client.patch(f"/api/notes/{a['id']}", json={"pinned": True})
    assert [n["title"] for n in client.get("/api/notes").json()] == ["Groceries", "Ideas"]
    assert [n["title"] for n in client.get("/api/notes?q=EGGS").json()] == ["Groceries"]

    updated = client.patch(f"/api/notes/{b['id']}", json={"content": "Changed"}).json()
    assert updated["content"] == "Changed" and updated["title"] == "Ideas"
    assert client.delete(f"/api/notes/{b['id']}").status_code == 204
    assert client.get(f"/api/notes/{b['id']}").status_code == 404


def test_notes_are_private(client, user_client) -> None:
    note = client.post("/api/notes", json={"title": "Secret"}).json()
    assert user_client.get("/api/notes").json() == []
    assert user_client.get(f"/api/notes/{note['id']}").status_code == 404
    assert user_client.patch(f"/api/notes/{note['id']}", json={"title": "x"}).status_code == 404
    assert user_client.delete(f"/api/notes/{note['id']}").status_code == 404


def test_note_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(notes_router, "MAX_NOTES", 1)
    client.post("/api/notes", json={})
    assert client.post("/api/notes", json={}).status_code == 409


def test_note_ai(client, fake_model) -> None:
    note = client.post("/api/notes", json={"title": "Draft", "content": "teh text"}).json()
    resp = client.post(
        f"/api/notes/{note['id']}/ai", json={"action": "improve", "model_id": "ollama:m"}
    )
    evts = events(resp.text)
    assert "".join(e.get("delta", "") for e in evts) == "Better text." and evts[-1] == {
        "done": True
    }
    system, user = fake_model.seen[0][0]
    assert "Improve this text" in system.content and '"Draft"' in system.content
    assert user.content == "teh text"


def test_note_ai_on_a_selection_and_custom(client, fake_model) -> None:
    note = client.post("/api/notes", json={"content": "whole note"}).json()
    client.post(
        f"/api/notes/{note['id']}/ai",
        json={
            "action": "custom",
            "model_id": "ollama:m",
            "text": "just this",
            "instruction": "Translate to French",
        },
    )
    system, user = fake_model.seen[0][0]
    assert system.content.startswith("Translate to French") and user.content == "just this"
    bad = client.post(
        f"/api/notes/{note['id']}/ai", json={"action": "custom", "model_id": "ollama:m"}
    )
    assert bad.status_code == 422
    empty = client.post("/api/notes", json={}).json()
    assert (
        client.post(
            f"/api/notes/{empty['id']}/ai", json={"action": "summarize", "model_id": "ollama:m"}
        ).status_code
        == 422
    )


def test_ask_in_chat(client) -> None:
    note = client.post("/api/notes", json={"title": "Trip", "content": "Tokyo in May"}).json()
    conv = client.post(f"/api/notes/{note['id']}/chat").json()
    assert conv["title"] == "About: Trip"
    detail = client.get(f"/api/conversations/{conv['id']}").json()
    assert "Tokyo in May" in detail["system_prompt"]


def test_deleting_a_user_deletes_their_notes(client, user_client) -> None:
    user_client.post("/api/notes", json={"title": "mine"})
    user_id = user_client.get("/api/auth/me").json()["id"]
    client.delete(f"/api/admin/users/{user_id}")
    from sqlmodel import Session, select

    from app.models import Note

    with Session(client.app.state.engine) as session:
        assert session.exec(select(Note)).all() == []

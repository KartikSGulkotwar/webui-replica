"""Saved memories: the API, which memories a reply sees, the chat context and the tool."""

import json

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, select

import app.memory as memory_module
from app.main import create_app
from app.memory import memory_context, relevant_memories
from app.models import Memory, Provider, User
from app.tools.registry import ToolContext, run_tool
from tests.conftest import signup

OLLAMA = "http://ollama.test"


def add(client, content: str) -> dict:
    resp = client.post("/api/memories", json={"content": content})
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- API --------------------------------------------------------------------------


def test_add_list_edit_delete(client) -> None:
    assert client.get("/api/memories").json() == {"enabled": True, "memories": []}
    first = add(client, "  Prefers   Python  ")
    second = add(client, "Works at Acme")
    assert first["content"] == "Prefers Python"  # whitespace tidied
    listed = client.get("/api/memories").json()["memories"]
    assert [m["content"] for m in listed] == ["Works at Acme", "Prefers Python"]  # newest first

    edited = client.patch(f"/api/memories/{first['id']}", json={"content": "Prefers Rust"})
    assert edited.json()["content"] == "Prefers Rust"
    assert client.delete(f"/api/memories/{second['id']}").status_code == 204
    assert [m["content"] for m in client.get("/api/memories").json()["memories"]] == [
        "Prefers Rust"
    ]
    assert client.delete("/api/memories").status_code == 204
    assert client.get("/api/memories").json()["memories"] == []


def test_duplicates_blank_and_limit(client, monkeypatch) -> None:
    a = add(client, "Likes tea")
    assert add(client, "likes TEA")["id"] == a["id"]  # same fact isn't stored twice
    assert client.post("/api/memories", json={"content": "   "}).status_code == 422
    monkeypatch.setattr(memory_module, "MAX_MEMORIES", 2)
    add(client, "Likes coffee")
    full = client.post("/api/memories", json={"content": "Likes juice"})
    assert full.status_code == 409 and "Delete some" in full.json()["detail"]


def test_memories_are_private(client, user_client) -> None:
    mine = add(client, "Admin secret preference")
    assert user_client.get("/api/memories").json()["memories"] == []
    assert (
        user_client.patch(f"/api/memories/{mine['id']}", json={"content": "x"}).status_code == 404
    )
    assert user_client.delete(f"/api/memories/{mine['id']}").status_code == 404
    user_client.delete("/api/memories")  # only clears their own
    assert len(client.get("/api/memories").json()["memories"]) == 1


def test_turning_memory_off(client) -> None:
    assert client.put("/api/memories/settings", json={"enabled": False}).json() == {
        "enabled": False
    }
    assert client.get("/api/memories").json()["enabled"] is False


def test_guests_have_memory(settings) -> None:
    settings.guest_access = True
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    with TestClient(app) as admin:
        signup(admin, "admin@example.com")
    with TestClient(app) as guest:
        guest.post("/api/auth/guest")
        add(guest, "Is trying the demo")
        assert len(guest.get("/api/memories").json()["memories"]) == 1


def test_deleting_a_user_deletes_their_memories(client, user_client, session) -> None:
    add(user_client, "Regular user fact")
    user_id = user_client.get("/api/auth/me").json()["id"]
    assert client.delete(f"/api/admin/users/{user_id}").status_code == 204
    assert session.exec(select(Memory).where(Memory.owner_id == user_id)).all() == []


# --- which memories a reply sees -----------------------------------------------------


def test_all_memories_when_there_are_few(client, session) -> None:
    for fact in ["Prefers Python", "Lives in Phoenix", "Has a dog named Rex"]:
        add(client, fact)
    user = session.exec(select(User)).first()
    assert [m.content for m in relevant_memories(session, user, "hello")] == [
        "Prefers Python",
        "Lives in Phoenix",
        "Has a dog named Rex",
    ]  # oldest first
    user.memory_enabled = False
    assert relevant_memories(session, user, "hello") == []


def test_many_memories_are_narrowed_to_matches_and_newest(client, session, monkeypatch) -> None:
    monkeypatch.setattr(memory_module, "SHOW_ALL_UP_TO", 3)
    monkeypatch.setattr(memory_module, "TOP_MATCHES", 1)
    monkeypatch.setattr(memory_module, "RECENT", 1)
    for fact in ["Has a dog named Rex", "Prefers Python", "Lives in Phoenix", "Likes jazz"]:
        add(client, fact)
    user = session.exec(select(User)).first()
    picked = [m.content for m in relevant_memories(session, user, "what's my dog called?")]
    assert picked == ["Has a dog named Rex", "Likes jazz"]  # best match + newest


def test_memory_context_wording() -> None:
    from datetime import datetime

    m = Memory(owner_id="u", content="Prefers Python", updated_at=datetime(2026, 10, 12))
    text = memory_context([m])
    assert "- Prefers Python (saved 2026-10-12)" in text and "<memories>" in text


# --- chat ---------------------------------------------------------------------------


def ollama_reply() -> bytes:
    return json.dumps({"message": {"content": "ok"}, "done": True}).encode() + b"\n"


@pytest.fixture
def ollama(session):
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()


@respx.mock
def test_chat_includes_memories_after_instructions(client, user_client, ollama) -> None:
    add(client, "Prefers concise answers")
    add(user_client, "Someone else's fact")
    route = respx.post(f"{OLLAMA}/api/chat").respond(content=ollama_reply())
    conv = client.post("/api/conversations", json={"system_prompt": "Be kind."}).json()["id"]
    client.post(
        "/api/chat/stream", json={"conversation_id": conv, "model_id": "ollama:m", "message": "hi"}
    )
    sent = json.loads(route.calls.last.request.content)["messages"]
    assert sent[0] == {"role": "system", "content": "Be kind."}
    assert sent[1]["role"] == "system" and "Prefers concise answers" in sent[1]["content"]
    assert "Someone else's fact" not in json.dumps(sent)
    assert sent[-1] == {"role": "user", "content": "hi"}

    client.put("/api/memories/settings", json={"enabled": False})
    client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:m", "action": "regenerate"},
    )
    assert "<memories>" not in route.calls.last.request.content.decode()


# --- the add_memory tool -----------------------------------------------------------


async def test_add_memory_tool(app, client, http) -> None:
    user_id = client.get("/api/auth/me").json()["id"]
    ctx = ToolContext(http=http, engine=app.state.engine, user_id=user_id)
    out = await run_tool("add_memory", {"content": "Prefers dark mode"}, ctx)
    assert not out.error and out.output == "Saved to memory: Prefers dark mode"
    assert [m["content"] for m in client.get("/api/memories").json()["memories"]] == [
        "Prefers dark mode"
    ]

    client.put("/api/memories/settings", json={"enabled": False})
    off = await run_tool("add_memory", {"content": "x"}, ctx)
    assert off.error and "turned memory off" in off.output
    nobody = await run_tool("add_memory", {"content": "x"}, ToolContext(http=http))
    assert nobody.error

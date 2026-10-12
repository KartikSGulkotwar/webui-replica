import json

import pytest
import respx
from fastapi.testclient import TestClient

from app.models import Provider
from tests.conftest import signup

OLLAMA = "http://ollama.test"
TAGS = {"models": [{"name": "qwen:0.5b"}, {"name": "allam:7b"}, {"name": "llama:1b"}]}


@pytest.fixture
def ollama(session):
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()


def reply(text: str) -> bytes:
    lines = [
        {"message": {"content": text}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    return b"".join(json.dumps(x).encode() + b"\n" for x in lines)


def menu(client) -> list[str]:
    return [m["id"] for m in client.get("/api/models").json()["models"]]


def persona(client, **overrides):
    body = {
        "name": "HR Helper",
        "description": "Answers from the handbook",
        "emoji": "📘",
        "base_model_id": "ollama:qwen:0.5b",
        "system_prompt": "You are the HR helper.",
        **overrides,
    }
    return client.post("/api/custom-models", json=body)


# --- admin model visibility & names ---------------------------------------------------


@respx.mock
def test_hide_and_rename_models(client, user_client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    assert menu(user_client) == ["ollama:allam:7b", "ollama:llama:1b", "ollama:qwen:0.5b"]

    assert (
        client.put(
            "/api/admin/models", json={"model_id": "ollama:allam:7b", "hidden": True}
        ).status_code
        == 204
    )
    client.put(
        "/api/admin/models",
        json={"model_id": "ollama:qwen:0.5b", "hidden": False, "display_name": "Qwen (fast)"},
    )

    models = user_client.get("/api/models").json()["models"]
    assert [(m["id"], m["name"]) for m in models] == [
        ("ollama:llama:1b", "llama:1b"),
        ("ollama:qwen:0.5b", "Qwen (fast)"),
    ]
    admin_view = {m["id"]: m for m in client.get("/api/admin/models").json()}
    assert admin_view["ollama:allam:7b"]["hidden"] is True
    assert admin_view["ollama:qwen:0.5b"]["display_name"] == "Qwen (fast)"
    assert admin_view["ollama:qwen:0.5b"]["name"] == "qwen:0.5b"

    # Back to defaults removes the override.
    client.put("/api/admin/models", json={"model_id": "ollama:allam:7b", "hidden": False})
    assert "ollama:allam:7b" in menu(user_client)


@respx.mock
def test_hidden_model_cannot_be_used_directly(client, user_client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("hi"))
    client.put("/api/admin/models", json={"model_id": "ollama:allam:7b", "hidden": True})
    conv = user_client.post("/api/conversations", json={}).json()["id"]
    blocked = user_client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:allam:7b", "message": "hi"},
    )
    assert blocked.status_code == 400 and "isn't available" in blocked.json()["detail"]
    # Admins can still test it.
    aconv = client.post("/api/conversations", json={}).json()["id"]
    assert (
        client.post(
            "/api/chat/stream",
            json={"conversation_id": aconv, "model_id": "ollama:allam:7b", "message": "hi"},
        ).status_code
        == 200
    )


def test_model_admin_routes_are_admin_only(user_client) -> None:
    assert user_client.get("/api/admin/models").status_code == 403
    assert (
        user_client.put("/api/admin/models", json={"model_id": "a:b", "hidden": True}).status_code
        == 403
    )


# --- custom models ----------------------------------------------------------------


@respx.mock
def test_create_and_list_custom_model(client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    created = persona(client)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (
        body["id"] == "hr-helper" and body["model_id"] == "persona:hr-helper" and body["is_owner"]
    )
    assert persona(client).json()["id"] == "hr-helper-2"  # unique IDs

    models = client.get("/api/models").json()
    custom = next(m for m in models["models"] if m["id"] == "persona:hr-helper")
    assert custom["provider_kind"] == "custom" and custom["emoji"] == "📘"
    assert custom["description"] == "Answers from the handbook"
    assert models["providers"][0] == {
        "id": "persona",
        "name": "Custom models",
        "kind": "custom",
        "ok": True,
        "error": None,
    }


@respx.mock
def test_chat_with_custom_model(client, ollama, session) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    route = respx.post(f"{OLLAMA}/api/chat").respond(
        content=reply("Per the handbook, 25 days [1].")
    )
    kb = client.post("/api/knowledge/collections", json={"name": "Handbook"}).json()["id"]
    client.post(
        "/api/knowledge/documents",
        files={"file": ("handbook.txt", b"Employees receive 25 days of paid vacation per year.")},
        data={"collection_id": kb},
    )
    persona(client, knowledge_ids=[kb])
    conv = client.post(
        "/api/conversations", json={"system_prompt": "Answer in one sentence."}
    ).json()["id"]

    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "persona:hr-helper",
            "message": "How many vacation days?",
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "qwen:0.5b"  # the base model answers
    roles = [(m["role"], m["content"][:30]) for m in sent["messages"]]
    assert roles[0] == ("system", "You are the HR helper.")
    assert roles[1] == ("system", "Answer in one sentence.")
    assert (
        roles[2][0] == "system" and "<sources>" in sent["messages"][2]["content"]
    )  # its knowledge
    first_event = json.loads(resp.text.splitlines()[0][6:])
    assert first_event["sources"][0]["filename"] == "handbook.txt"
    saved = client.get(f"/api/conversations/{conv}").json()["messages"][-1]
    assert saved["model_id"] == "persona:hr-helper"


@respx.mock
def test_private_and_public_visibility(client, user_client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("ok"))
    persona(client, name="Admin private")
    persona(client, name="Company bot", visibility="public")
    mine = persona(user_client, name="My tutor").json()

    assert {m["name"] for m in user_client.get("/api/custom-models").json()} == {
        "Company bot",
        "My tutor",
    }
    assert [m["id"] for m in client.get("/api/custom-models").json()] == [
        "admin-private",
        "company-bot",
    ]
    assert "persona:admin-private" not in menu(user_client)
    assert user_client.get("/api/custom-models/admin-private").status_code == 404

    conv = user_client.post("/api/conversations", json={}).json()["id"]

    def chat(model_id):
        return user_client.post(
            "/api/chat/stream",
            json={"conversation_id": conv, "model_id": model_id, "message": "hi"},
        )

    assert chat("persona:company-bot").status_code == 200
    assert chat(f"persona:{mine['id']}").status_code == 200
    assert chat("persona:admin-private").status_code == 400
    assert chat("persona:does-not-exist").status_code == 400

    # Users can't publish, nor edit/delete someone else's public model.
    assert persona(user_client, name="Spam", visibility="public").status_code == 403
    pub = {"name": "x", "base_model_id": "ollama:qwen:0.5b"}
    assert user_client.put("/api/custom-models/company-bot", json=pub).status_code == 403
    assert user_client.delete("/api/custom-models/company-bot").status_code == 403
    # Admins may edit a user's private model? No: it's private, so they don't see it.
    assert client.put(f"/api/custom-models/{mine['id']}", json=pub).status_code == 404


@respx.mock
def test_custom_model_validation(client, user_client, ollama, app) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    assert persona(client, base_model_id="ollama:missing").status_code == 422
    assert persona(client, base_model_id="no-colon").status_code == 422
    assert persona(client, base_model_id="persona:hr-helper").status_code == 422
    assert persona(client, name="  ").status_code == 422
    other_kb = client.post("/api/knowledge/collections", json={"name": "Admin KB"}).json()["id"]
    assert persona(user_client, knowledge_ids=[other_kb]).status_code == 404  # not theirs

    client.put("/api/admin/models", json={"model_id": "ollama:allam:7b", "hidden": True})
    assert persona(user_client, base_model_id="ollama:allam:7b").status_code == 422
    # Admins may wrap a hidden model in a curated public assistant.
    assert (
        persona(
            client, name="Arabic tutor", base_model_id="ollama:allam:7b", visibility="public"
        ).status_code
        == 201
    )
    assert "persona:arabic-tutor" in menu(user_client)


@respx.mock
def test_custom_model_hidden_when_base_model_is_gone(client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    persona(client)
    respx.get(f"{OLLAMA}/api/tags").respond(json={"models": [{"name": "llama:1b"}]})
    assert "persona:hr-helper" not in menu(client)
    # Still listed in the workspace, so it can be fixed.
    assert client.get("/api/custom-models").json()[0]["id"] == "hr-helper"


@respx.mock
def test_update_and_delete_custom_model(client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json=TAGS)
    persona(client)
    updated = client.put(
        "/api/custom-models/hr-helper",
        json={
            "name": "HR Assistant",
            "emoji": "🧑‍💼",
            "base_model_id": "ollama:llama:1b",
            "system_prompt": "Be kind.",
        },
    ).json()
    assert (updated["id"], updated["name"], updated["base_model_id"]) == (
        "hr-helper",
        "HR Assistant",
        "ollama:llama:1b",
    )
    assert client.delete("/api/custom-models/hr-helper").status_code == 204
    assert client.get("/api/custom-models").json() == []


def test_deleting_user_removes_their_custom_models(client, app, session) -> None:
    from app.models import CustomModel

    with TestClient(app) as other:
        user = signup(other, "maker@example.com")
    session.add(
        CustomModel(id="theirs", owner_id=user["id"], name="Theirs", base_model_id="ollama:x")
    )
    session.commit()
    client.delete(f"/api/admin/users/{user['id']}")
    session.expire_all()
    assert session.get(CustomModel, "theirs") is None


@respx.mock
def test_provider_with_every_model_hidden_leaves_the_menu(client, user_client, ollama) -> None:
    respx.get(f"{OLLAMA}/api/tags").respond(json={"models": [{"name": "allam:7b"}]})
    client.put("/api/admin/models", json={"model_id": "ollama:allam:7b", "hidden": True})
    assert user_client.get("/api/models").json() == {"models": [], "providers": []}

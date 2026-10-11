import json

import pytest
import respx
from fastapi.testclient import TestClient

from app.models import Message, Provider
from tests.conftest import signup

OLLAMA = "http://ollama.test"


@pytest.fixture
def provider(session) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()


def reply(text: str) -> bytes:
    lines = [
        {"message": {"content": text}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    return b"".join(json.dumps(x).encode() + b"\n" for x in lines)


def chat(client, conv, model="ollama:m", **body):
    resp = client.post(
        "/api/chat/stream", json={"conversation_id": conv, "model_id": model, **body}
    )
    return resp


def messages(client, conv):
    return [
        (m["role"], m["content"])
        for m in client.get(f"/api/conversations/{conv}").json()["messages"]
    ]


def new_conv(client, **body) -> str:
    return client.post("/api/conversations", json=body).json()["id"]


# --- regenerate / edit ------------------------------------------------------------


@respx.mock
def test_regenerate_replaces_last_reply(client, provider) -> None:
    route = respx.post(f"{OLLAMA}/api/chat")
    route.respond(content=reply("first answer"))
    conv = new_conv(client)
    chat(client, conv, message="Question?")

    route.respond(content=reply("second answer"))
    resp = chat(client, conv, model="ollama:other", action="regenerate")

    assert resp.status_code == 200
    detail = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert [(m["role"], m["content"], m["model_id"]) for m in detail] == [
        ("user", "Question?", None),
        ("assistant", "second answer", "ollama:other"),
    ]
    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"] == [{"role": "user", "content": "Question?"}]


@respx.mock
def test_regenerate_after_failed_reply(client, provider) -> None:
    """If the last reply never arrived, regenerate just answers the last question."""
    respx.post(f"{OLLAMA}/api/chat").respond(500, text="boom")
    conv = new_conv(client)
    chat(client, conv, message="Question?")
    assert messages(client, conv) == [("user", "Question?")]

    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("ok now"))
    chat(client, conv, action="regenerate")
    assert messages(client, conv) == [("user", "Question?"), ("assistant", "ok now")]


def test_regenerate_needs_a_question(client, provider) -> None:
    conv = new_conv(client)
    resp = chat(client, conv, action="regenerate")
    assert resp.status_code == 400


@respx.mock
def test_edit_rewrites_message_and_drops_later_turns(client, provider) -> None:
    route = respx.post(f"{OLLAMA}/api/chat")
    route.respond(content=reply("A1"))
    conv = new_conv(client)
    chat(client, conv, message="Q1")
    chat(client, conv, message="Q2")
    first_q = client.get(f"/api/conversations/{conv}").json()["messages"][0]["id"]

    route.respond(content=reply("A1 again"))
    resp = chat(client, conv, action="edit", message_id=first_q, message="Q1 (edited)")

    assert resp.status_code == 200
    assert messages(client, conv) == [("user", "Q1 (edited)"), ("assistant", "A1 again")]
    assert json.loads(route.calls.last.request.content)["messages"] == [
        {"role": "user", "content": "Q1 (edited)"}
    ]


@respx.mock
def test_edit_rejects_replies_and_unknown_ids(client, provider) -> None:
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("A"))
    conv = new_conv(client)
    chat(client, conv, message="Q")
    reply_id = client.get(f"/api/conversations/{conv}").json()["messages"][1]["id"]
    assert chat(client, conv, action="edit", message_id=reply_id, message="x").status_code == 404
    assert chat(client, conv, action="edit", message_id=99999, message="x").status_code == 404


@pytest.mark.parametrize(
    "body",
    [{"action": "send"}, {"action": "edit", "message": "x"}, {"action": "edit", "message_id": 1}],
)
def test_action_validation(client, body) -> None:
    conv = new_conv(client)
    assert chat(client, conv, **body).status_code == 422


# --- system prompt ----------------------------------------------------------------


@respx.mock
def test_system_prompt_is_sent_first(client, provider) -> None:
    route = respx.post(f"{OLLAMA}/api/chat").respond(content=reply("Arr"))
    conv = new_conv(client, system_prompt="  Talk like a pirate. ")
    assert client.get(f"/api/conversations/{conv}").json()["system_prompt"] == "Talk like a pirate."

    chat(client, conv, message="Hello")
    assert json.loads(route.calls.last.request.content)["messages"] == [
        {"role": "system", "content": "Talk like a pirate."},
        {"role": "user", "content": "Hello"},
    ]
    # Not stored as a message in the conversation.
    assert messages(client, conv) == [("user", "Hello"), ("assistant", "Arr")]

    client.patch(f"/api/conversations/{conv}", json={"system_prompt": ""})
    chat(client, conv, message="Again")
    assert json.loads(route.calls.last.request.content)["messages"][0]["role"] == "user"


# --- rating -----------------------------------------------------------------------


@respx.mock
def test_rating_replies(client, provider, session) -> None:
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("A"))
    conv = new_conv(client)
    chat(client, conv, message="Q")
    q_id, a_id = [m["id"] for m in client.get(f"/api/conversations/{conv}").json()["messages"]]
    url = f"/api/conversations/{conv}/messages/{a_id}/rating"

    up = client.put(url, json={"rating": 1, "comment": "  spot on "})
    assert up.json()["rating"] == 1 and up.json()["rating_comment"] == "spot on"
    assert client.get(f"/api/conversations/{conv}").json()["messages"][1]["rating"] == 1

    cleared = client.put(url, json={"rating": None, "comment": "ignored"}).json()
    assert cleared["rating"] is None and cleared["rating_comment"] is None

    assert client.put(url, json={"rating": 5}).status_code == 422
    user_msg = f"/api/conversations/{conv}/messages/{q_id}/rating"
    assert client.put(user_msg, json={"rating": 1}).status_code == 400
    other_conv = new_conv(client)
    wrong = f"/api/conversations/{other_conv}/messages/{a_id}/rating"
    assert client.put(wrong, json={"rating": 1}).status_code == 404


def test_cannot_rate_someone_elses_message(client, user_client, session) -> None:
    conv = new_conv(client)
    msg = Message(conversation_id=conv, role="assistant", content="A")
    session.add(msg)
    session.commit()
    url = f"/api/conversations/{conv}/messages/{msg.id}/rating"
    assert user_client.put(url, json={"rating": -1}).status_code == 404


# --- search, pin, archive -----------------------------------------------------------


def add_messages(session, conv: str, *contents: str) -> None:
    for c in contents:
        session.add(Message(conversation_id=conv, role="user", content=c))
    session.commit()


def test_search_titles_and_messages_with_snippets(client, session) -> None:
    trip = new_conv(client, title="Trip to Lisbon")
    code = new_conv(client, title="Python help")
    add_messages(session, code, "How do I sort a list?", "Explain " + "x" * 100 + " lisbon sorting")
    new_conv(client, title="Unrelated")

    results = client.get("/api/conversations", params={"q": "LISBON"}).json()
    by_id = {r["id"]: r for r in results}
    assert set(by_id) == {trip, code}
    assert by_id[trip]["snippet"] is None  # title match only
    assert by_id[code]["snippet"].startswith("…") and "lisbon sorting" in by_id[code]["snippet"]

    assert client.get("/api/conversations", params={"q": "   "}).json()[0]["snippet"] is None


def test_search_treats_wildcards_literally(client, session) -> None:
    conv = new_conv(client, title="Plain")
    add_messages(session, conv, "100% sure", "snake_case")
    new_conv(client, title="Other")
    assert [r["id"] for r in client.get("/api/conversations", params={"q": "%"}).json()] == [conv]
    assert [r["id"] for r in client.get("/api/conversations", params={"q": "_"}).json()] == [conv]


def test_search_only_finds_own_chats(client, user_client, session) -> None:
    conv = new_conv(client, title="Secret plans")
    add_messages(session, conv, "secret")
    assert user_client.get("/api/conversations", params={"q": "secret"}).json() == []


def test_pin_and_archive(client) -> None:
    a = new_conv(client, title="A")
    b = new_conv(client, title="B")
    c = new_conv(client, title="C")
    ids = lambda **p: [x["id"] for x in client.get("/api/conversations", params=p).json()]  # noqa: E731
    assert ids() == [c, b, a]

    pinned = client.patch(f"/api/conversations/{a}", json={"pinned": True}).json()
    assert pinned["pinned"] is True
    assert ids() == [a, c, b]  # pinned first; pinning doesn't change updated order

    client.patch(f"/api/conversations/{a}", json={"archived": True})
    assert ids() == [c, b]
    archived = client.get("/api/conversations", params={"archived": True}).json()
    assert [x["id"] for x in archived] == [a] and archived[0]["pinned"] is False  # unpinned

    client.patch(f"/api/conversations/{a}", json={"archived": False})
    assert ids() == [c, b, a]
    # Archived chats can still be opened.
    assert client.get(f"/api/conversations/{a}").status_code == 200


def test_partial_update_keeps_other_fields(client) -> None:
    conv = new_conv(client, title="Keep me", system_prompt="Be brief")
    client.patch(f"/api/conversations/{conv}", json={"pinned": True})
    detail = client.get(f"/api/conversations/{conv}").json()
    assert (detail["title"], detail["system_prompt"], detail["pinned"]) == (
        "Keep me",
        "Be brief",
        True,
    )
    assert client.patch(f"/api/conversations/{conv}", json={"title": "  "}).status_code == 422


# --- share --------------------------------------------------------------------------


def test_share_snapshot(client, app, session) -> None:
    conv = new_conv(client, title="How to bake bread", system_prompt="hidden instructions")
    add_messages(session, conv, "first message")

    share = client.post(f"/api/conversations/{conv}/share").json()
    sid = share["share_id"]
    assert len(sid) >= 20

    with TestClient(app) as stranger:  # not signed in
        public = stranger.get(f"/api/shared/{sid}")
        assert public.status_code == 200
        body = public.json()
        assert body["title"] == "How to bake bread"
        assert [m["content"] for m in body["messages"]] == ["first message"]
        assert "hidden instructions" not in public.text  # system prompt stays private

        add_messages(session, conv, "added after sharing")
        assert len(stranger.get(f"/api/shared/{sid}").json()["messages"]) == 1  # snapshot

        again = client.post(f"/api/conversations/{conv}/share").json()
        assert again["share_id"] == sid  # same link, refreshed content
        assert len(stranger.get(f"/api/shared/{sid}").json()["messages"]) == 2

        listed = client.get("/api/conversations").json()[0]
        assert listed["shared"] is True
        assert client.get(f"/api/conversations/{conv}").json()["share_id"] == sid

        assert client.delete(f"/api/conversations/{conv}/share").status_code == 204
        assert stranger.get(f"/api/shared/{sid}").status_code == 404
        assert client.get(f"/api/conversations/{conv}").json()["share_id"] is None


def test_deleting_chat_removes_its_share(client, anon_client) -> None:
    conv = new_conv(client)
    sid = client.post(f"/api/conversations/{conv}/share").json()["share_id"]
    client.delete(f"/api/conversations/{conv}")
    assert anon_client.get(f"/api/shared/{sid}").status_code == 404


def test_only_owner_can_share(client, user_client) -> None:
    conv = new_conv(client)
    assert user_client.post(f"/api/conversations/{conv}/share").status_code == 404
    assert user_client.delete(f"/api/conversations/{conv}/share").status_code == 404


def test_deleting_user_removes_their_shares(client, app, anon_client) -> None:
    with TestClient(app) as other:
        user = signup(other, "sharer@example.com")
        client.patch(f"/api/admin/users/{user['id']}", json={"role": "user"})
        conv = new_conv(other)
        sid = other.post(f"/api/conversations/{conv}/share").json()["share_id"]
        client.delete(f"/api/admin/users/{user['id']}")
    assert anon_client.get(f"/api/shared/{sid}").status_code == 404


# --- export -------------------------------------------------------------------------


def test_export_all_includes_archived(client, user_client, session) -> None:
    a = new_conv(client, title="One")
    b = new_conv(client, title="Two")
    add_messages(session, a, "hello")
    client.patch(f"/api/conversations/{b}", json={"archived": True})
    new_conv(user_client, title="Not mine")

    exported = client.get("/api/conversations/export").json()
    assert [(c["title"], len(c["messages"])) for c in exported] == [("One", 1), ("Two", 0)]
    assert exported[1]["archived"] is True

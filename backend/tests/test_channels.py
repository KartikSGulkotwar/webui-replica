"""Channels: admin management, messages, polling, reactions, and models replying."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

import app.routers.channels as channels_router
from app.catalog import ResolvedModel
from app.models import ChannelMessage
from app.schemas import StreamChunk
from tests.test_tool_calling import ScriptedProvider


@pytest.fixture
def channel(client) -> dict:
    resp = client.post("/api/channels", json={"name": "  General Chat ", "description": "Hi"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def post(client, channel_id: str, content: str, **extra) -> dict:
    resp = client.post(f"/api/channels/{channel_id}/messages", json={"content": content, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_channel_management(client, user_client, channel) -> None:
    assert channel["name"] == "general-chat"
    assert client.post("/api/channels", json={"name": "General  Chat"}).status_code == 409
    assert user_client.post("/api/channels", json={"name": "mine"}).status_code == 403
    assert [c["name"] for c in user_client.get("/api/channels").json()] == ["general-chat"]
    renamed = client.patch(
        f"/api/channels/{channel['id']}", json={"name": "#general", "description": ""}
    ).json()
    assert renamed["name"] == "general"
    post(user_client, channel["id"], "hello")
    assert user_client.delete(f"/api/channels/{channel['id']}").status_code == 403
    assert client.delete(f"/api/channels/{channel['id']}").status_code == 204
    assert client.get("/api/channels").json() == []


def test_messages_paging_and_polling(client, user_client, channel) -> None:
    cid = channel["id"]
    for i in range(5):
        post(client, cid, f"m{i}")
    page = user_client.get(f"/api/channels/{cid}/messages?limit=3").json()
    assert [m["content"] for m in page["messages"]] == ["m2", "m3", "m4"] and page["has_more"]
    assert page["messages"][0]["author"] == "Admin"
    older = user_client.get(
        f"/api/channels/{cid}/messages?limit=3&before={page['messages'][0]['id']}"
    ).json()
    assert [m["content"] for m in older["messages"]] == ["m0", "m1"] and not older["has_more"]

    # Polling returns what's new or changed since the last answer.
    reply = post(user_client, cid, "answer", reply_to=page["messages"][-1]["id"])
    polled = user_client.get(f"/api/channels/{cid}/messages", params={"since": page["now"]}).json()
    assert reply["id"] in [m["id"] for m in polled["messages"]]
    assert reply["reply_to"] == page["messages"][-1]["id"] and reply["author"] == "Regular User"
    later = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    assert (
        user_client.get(f"/api/channels/{cid}/messages", params={"since": later}).json()["messages"]
        == []
    )


def test_edit_delete_and_permissions(client, user_client, channel) -> None:
    cid = channel["id"]
    mine = post(user_client, cid, "typo")
    theirs = post(client, cid, "admin says")
    edited = user_client.patch(
        f"/api/channels/{cid}/messages/{mine['id']}", json={"content": "fixed"}
    ).json()
    assert edited["content"] == "fixed" and edited["edited"]
    assert (
        user_client.patch(
            f"/api/channels/{cid}/messages/{theirs['id']}", json={"content": "x"}
        ).status_code
        == 403
    )
    assert user_client.delete(f"/api/channels/{cid}/messages/{theirs['id']}").status_code == 403
    # Admins can delete anyone's; deleted messages stay as empty placeholders.
    assert client.delete(f"/api/channels/{cid}/messages/{mine['id']}").status_code == 204
    shown = client.get(f"/api/channels/{cid}/messages").json()["messages"]
    gone = next(m for m in shown if m["id"] == mine["id"])
    assert gone["deleted"] and gone["content"] == "" and gone["reactions"] == []


def test_reactions(client, user_client, channel) -> None:
    cid = channel["id"]
    msg = post(client, cid, "party")
    url = f"/api/channels/{cid}/messages/{msg['id']}/reactions"
    user_client.put(url, json={"emoji": "🎉"})
    out = client.put(url, json={"emoji": "🎉"}).json()
    assert out["reactions"] == [{"emoji": "🎉", "count": 2, "mine": True}]
    out = client.put(url, json={"emoji": "🎉"}).json()  # toggles off
    assert out["reactions"] == [{"emoji": "🎉", "count": 1, "mine": False}]
    assert client.put(url, json={"emoji": "💩"}).status_code == 422


def test_model_replies_in_channel(client, user_client, channel, monkeypatch) -> None:
    provider = ScriptedProvider([[StreamChunk(delta="Paris."), StreamChunk(done=True)]])
    monkeypatch.setattr(
        channels_router, "pick_model", lambda *a: (provider, ResolvedModel("ollama", "m"))
    )
    cid = channel["id"]
    post(client, cid, "We're planning a trip to France")
    ask = post(user_client, cid, "@m what's the capital?")
    # Only the author of the message can ask for the reply.
    assert (
        client.post(
            f"/api/channels/{cid}/ai", json={"model_id": "ollama:m", "message_id": ask["id"]}
        ).status_code
        == 403
    )
    resp = user_client.post(
        f"/api/channels/{cid}/ai", json={"model_id": "ollama:m", "message_id": ask["id"]}
    )
    evts = [json.loads(x[6:]) for x in resp.text.split("\n\n") if x.startswith("data:")]
    assert "".join(e.get("delta", "") for e in evts) == "Paris." and evts[-1] == {"done": True}

    system, context = provider.seen[0][0]
    assert "#general-chat" in system.content and "Regular User mentioned you" in system.content
    assert context.content == (
        "Admin: We're planning a trip to France\n\nRegular User: @m what's the capital?"
    )
    last = client.get(f"/api/channels/{cid}/messages").json()["messages"][-1]
    assert last["author"] == "m" and last["model_id"] == "ollama:m"
    assert last["content"] == "Paris." and last["reply_to"] == ask["id"]
    # Whoever asked can delete the model's reply.
    assert user_client.delete(f"/api/channels/{cid}/messages/{last['id']}").status_code == 204


def test_deleting_a_user_removes_their_channel_posts(client, user_client, channel) -> None:
    post(user_client, channel["id"], "bye")
    user_id = user_client.get("/api/auth/me").json()["id"]
    client.delete(f"/api/admin/users/{user_id}")
    with Session(client.app.state.engine) as session:
        assert session.exec(select(ChannelMessage)).all() == []

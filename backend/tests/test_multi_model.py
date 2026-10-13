"""Side-by-side replies, the arena, the leaderboard and usage analytics."""

import asyncio
import json

import httpx
import pytest
import respx

from app.models import Message, Provider
from app.routers.chat import merge, thread_for

OLLAMA = "http://ollama.test"


def ollama_reply(model: str, text: str) -> bytes:
    lines = [
        {"message": {"content": text}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 7, "eval_count": 3},
    ]
    return b"".join(json.dumps(x).encode() + b"\n" for x in lines)


@pytest.fixture
def ollama(session):
    """Ollama whose models answer "<model> says hi" and record what they were sent."""
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()
    seen: dict[str, list] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.setdefault(body["model"], []).append(body["messages"])
        return httpx.Response(200, content=ollama_reply(body["model"], f"{body['model']} says hi"))

    with respx.mock:
        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=answer)
        respx.get(f"{OLLAMA}/api/tags").respond(
            json={"models": [{"name": n} for n in ("a", "b", "c", "d")]}
        )
        yield seen


@pytest.fixture
def conv(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


def stream(client, conv: str, **body) -> list[dict]:
    resp = client.post("/api/chat/stream", json={"conversation_id": conv, **body})
    assert resp.status_code == 200, resp.text
    return [json.loads(line[6:]) for line in resp.text.split("\n\n") if line.startswith("data:")]


def replies(client, conv: str) -> list[dict]:
    return [
        m
        for m in client.get(f"/api/conversations/{conv}").json()["messages"]
        if m["role"] == "assistant"
    ]


# --- helpers ------------------------------------------------------------------------


def test_each_model_continues_its_own_thread() -> None:
    def m(i, role, content, model=None, slot=None):
        return Message(
            id=i, conversation_id="c", role=role, content=content, model_id=model, slot=slot
        )

    messages = [
        m(1, "user", "q1"),
        m(2, "assistant", "A1", "x:a", 0),
        m(3, "assistant", "B1", "x:b", 1),
        m(4, "user", "q2"),
    ]
    assert [c.content for c in thread_for(messages, "x:b")] == ["q1", "B1", "q2"]
    # A model that wasn't there continues from the first column.
    assert [c.content for c in thread_for(messages, "x:c")] == ["q1", "A1", "q2"]


async def test_merge_interleaves_streams() -> None:
    async def slow(name, delay):
        for i in range(2):
            await asyncio.sleep(delay)
            yield f"{name}{i}"

    out = [e async for e in merge([slow("a", 0.02), slow("b", 0.005)])]
    assert sorted(out) == ["a0", "a1", "b0", "b1"] and out[0] == "b0"


# --- side by side --------------------------------------------------------------------


def test_side_by_side_replies(client, conv, ollama) -> None:
    events = stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="hi")
    assert events[0] == {
        "replies": [{"model_id": "ollama:a", "slot": 0}, {"model_id": "ollama:b", "slot": 1}],
        "blind": False,
    }
    text = {0: "", 1: ""}
    for e in events[1:-1]:
        assert "reply" in e  # every event names its reply
        text[e["reply"]] += e.get("delta", "")
    assert text == {0: "ollama:a says hi".replace("ollama:", ""), 1: "b says hi"}
    assert events[-1] == {"done": True}  # the whole turn is over

    saved = replies(client, conv)
    assert sorted((r["slot"], r["model_id"], r["content"]) for r in saved) == [
        (0, "ollama:a", "a says hi"),
        (1, "ollama:b", "b says hi"),
    ]
    # Usage is kept for analytics.
    assert all(r["blind"] is False for r in saved)

    # Next turn: each model sees its own earlier answer.
    stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="again")
    assert ollama["b"][-1][1] == {"role": "assistant", "content": "b says hi"}
    assert ollama["a"][-1][1] == {"role": "assistant", "content": "a says hi"}


def test_regenerate_one_reply_keeps_the_other(client, conv, ollama) -> None:
    stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="hi")
    b = next(r for r in replies(client, conv) if r["slot"] == 1)
    events = stream(client, conv, model_id="ollama:c", action="regenerate", message_id=b["id"])
    assert "reply" not in events[-1]  # a single reply streams as usual
    saved = sorted((r["slot"], r["model_id"]) for r in replies(client, conv))
    assert saved == [(0, "ollama:a"), (1, "ollama:c")]
    # The regenerated reply didn't see its sibling as part of the conversation.
    assert [m["role"] for m in ollama["c"][-1]] == ["user"]

    # Regenerating without message_id replaces the whole turn.
    stream(client, conv, model_id="ollama:d", action="regenerate")
    assert [(r["slot"], r["model_id"]) for r in replies(client, conv)] == [(None, "ollama:d")]


def test_side_by_side_limits(client, conv, ollama) -> None:
    too_many = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:a",
            "model_ids": ["ollama:b", "ollama:c", "ollama:d"],
            "message": "hi",
        },
    )
    assert too_many.status_code == 422
    stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="hi")
    one = replies(client, conv)[0]
    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:a",
            "model_ids": ["ollama:b"],
            "action": "regenerate",
            "message_id": one["id"],
        },
    )
    assert resp.status_code == 422


# --- arena ----------------------------------------------------------------------------


def set_arena(client, models: list[str]) -> None:
    resp = client.put(
        "/api/admin/settings",
        json={"enable_signup": True, "default_user_role": "user", "arena_models": models},
    )
    assert resp.status_code == 200, resp.text


def test_arena_hides_models_until_vote(client, conv, ollama) -> None:
    assert (
        client.post(
            "/api/chat/stream",
            json={"conversation_id": conv, "model_id": "arena:blind", "message": "hi"},
        ).status_code
        == 400
    )  # no arena models yet
    set_arena(client, ["ollama:a", "ollama:b", "ollama:c"])
    assert client.get("/api/models").json()["models"][0]["id"] == "arena:blind"

    events = stream(client, conv, model_id="arena:blind", message="hi")
    assert events[0] == {
        "replies": [{"model_id": None, "slot": 0}, {"model_id": None, "slot": 1}],
        "blind": True,
    }
    hidden = replies(client, conv)
    assert [r["model_id"] for r in hidden] == [None, None] and all(r["blind"] for r in hidden)
    assert len(ollama) == 2  # two different models answered

    # Arena replies can't be regenerated one by one.
    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:a",
            "action": "regenerate",
            "message_id": hidden[0]["id"],
        },
    )
    assert resp.status_code == 400

    a, b = sorted(hidden, key=lambda r: r["slot"])
    voted = client.put(
        f"/api/conversations/{conv}/ratings", json={"ratings": {a["id"]: 1, b["id"]: -1}}
    ).json()
    shown = [m for m in voted if m["role"] == "assistant"]
    assert sorted(m["model_id"] for m in shown) == sorted(f"ollama:{k}" for k in ollama)
    assert [m["rating"] for m in sorted(shown, key=lambda m: m["slot"])] == [1, -1]

    board = client.get("/api/admin/leaderboard").json()
    assert board[0]["model_id"] == a_model(shown, 0) and board[0]["elo"] == 1016
    assert board[0]["wins"] == 1 and board[-1]["losses"] == 1


def a_model(shown: list[dict], slot: int) -> str:
    return next(m["model_id"] for m in shown if m["slot"] == slot)


def test_arena_settings_validation(client) -> None:
    for bad in (["persona:x", "ollama:a"], ["nocolon"], ["arena:blind"]):
        resp = client.put(
            "/api/admin/settings",
            json={"enable_signup": True, "default_user_role": "user", "arena_models": bad},
        )
        assert resp.status_code == 422, bad
    set_arena(client, ["ollama:a", "ollama:a", "ollama:b"])
    assert client.get("/api/admin/settings").json()["arena_models"] == ["ollama:a", "ollama:b"]
    # Saving other settings keeps the arena list.
    client.put("/api/admin/settings", json={"enable_signup": True, "default_user_role": "user"})
    assert client.get("/api/admin/settings").json()["arena_models"] == ["ollama:a", "ollama:b"]


def test_arena_cannot_mix_with_models(client, conv, ollama) -> None:
    set_arena(client, ["ollama:a", "ollama:b"])
    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:c",
            "model_ids": ["arena:blind"],
            "message": "hi",
        },
    )
    assert resp.status_code == 422


def test_shared_snapshot_hides_unvoted_arena(client, conv, ollama) -> None:
    set_arena(client, ["ollama:a", "ollama:b"])
    stream(client, conv, model_id="arena:blind", message="hi")
    share = client.post(f"/api/conversations/{conv}/share").json()["share_id"]
    shared = client.get(f"/api/shared/{share}").json()["messages"]
    assert [m["model_id"] for m in shared if m["role"] == "assistant"] == [None, None]


# --- leaderboard & analytics -------------------------------------------------------------


def test_leaderboard_from_side_by_side_ratings(client, conv, ollama) -> None:
    stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="q1")
    stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="q2")
    first, second = replies(client, conv)[:2], replies(client, conv)[2:]
    a1 = next(r for r in first if r["model_id"] == "ollama:a")
    b2 = next(r for r in second if r["model_id"] == "ollama:b")
    a2 = next(r for r in second if r["model_id"] == "ollama:a")
    client.put(f"/api/conversations/{conv}/messages/{a1['id']}/rating", json={"rating": 1})
    client.put(f"/api/conversations/{conv}/ratings", json={"ratings": {a2["id"]: 1, b2["id"]: 1}})
    board = {r["model_id"]: r for r in client.get("/api/admin/leaderboard").json()}
    assert board["ollama:a"]["wins"] == 1 and board["ollama:a"]["ties"] == 1
    assert board["ollama:b"]["losses"] == 1 and board["ollama:b"]["ties"] == 1
    assert board["ollama:a"]["likes"] == 2 and board["ollama:b"]["likes"] == 1
    assert board["ollama:a"]["elo"] > 1000 > board["ollama:b"]["elo"]


def test_usage_report(client, user_client, conv, ollama) -> None:
    stream(client, conv, model_id="ollama:a", model_ids=["ollama:b"], message="hi")
    report = client.get("/api/admin/analytics?days=7").json()
    assert report["days"] == 7 and len(report["daily"]) == 7
    today = report["daily"][-1]
    assert today["messages"] == 1 and today["replies"] == 2 and today["active_users"] == 1
    assert today["tokens"] == 20  # (7 prompt + 3 completion) per reply
    by_model = {m["model_id"]: m for m in report["models"]}
    assert by_model["ollama:a"] == {
        "model_id": "ollama:a",
        "replies": 1,
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "likes": 0,
        "dislikes": 0,
    }
    assert report["totals"]["users"] == 2 and report["totals"]["messages"] == 1
    assert user_client.get("/api/admin/analytics").status_code == 403
    assert user_client.get("/api/admin/leaderboard").status_code == 403

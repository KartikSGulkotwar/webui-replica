import json

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel
from starlette.requests import Request

from app.main import create_app
from app.models import Provider
from app.ratelimit import RateLimiter, client_ip


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_limit_then_blocks() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, window=60, clock=clock)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    assert limiter.hit("a") == pytest.approx(60)
    assert limiter.hit("b") is None  # other clients unaffected


def test_limiter_window_slides() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, window=60, clock=clock)
    limiter.hit("a")
    clock.now += 30
    limiter.hit("a")
    assert limiter.hit("a") == pytest.approx(30)
    clock.now += 30.1  # first hit expired
    assert limiter.hit("a") is None


def test_limiter_sweeps_idle_keys() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, window=60, clock=clock)
    for i in range(100):
        limiter.hit(f"ip{i}")
    clock.now += 61
    limiter.hit("new")
    assert list(limiter._hits) == ["new"]


def make_request(xff: str | None, peer: str = "10.0.0.1") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("xff", "hops", "expected"),
    [
        (None, 0, "10.0.0.1"),
        ("6.6.6.6", 0, "10.0.0.1"),  # header ignored unless proxies are trusted
        ("203.0.113.5", 1, "203.0.113.5"),
        ("6.6.6.6, 203.0.113.5", 1, "203.0.113.5"),  # forged left entry ignored
        ("6.6.6.6, 203.0.113.5, 10.1.1.1", 2, "203.0.113.5"),
        (None, 1, "10.0.0.1"),  # missing header falls back to the socket
    ],
)
def test_client_ip(xff, hops, expected) -> None:
    assert client_ip(make_request(xff), hops) == expected


@respx.mock
def test_chat_stream_is_rate_limited(settings) -> None:
    settings.chat_rate_limit_per_minute = 2
    settings.trusted_proxy_hops = 1
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    reply = json.dumps({"message": {"content": "ok"}, "done": True}).encode() + b"\n"
    respx.post("http://o.test/api/chat").respond(content=reply)

    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            session.add(Provider(id="o", name="O", kind="ollama", base_url="http://o.test"))
            session.commit()
        conv = client.post("/api/conversations", json={}).json()["id"]
        body = {"conversation_id": conv, "model_id": "o:m", "message": "hi"}

        def send(ip: str):
            return client.post("/api/chat/stream", json=body, headers={"X-Forwarded-For": ip})

        assert send("1.1.1.1").status_code == 200
        assert send("1.1.1.1").status_code == 200
        blocked = send("1.1.1.1")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
        assert "Too many messages" in blocked.json()["detail"]
        assert send("2.2.2.2").status_code == 200

        # Blocked requests don't store the user message.
        messages = client.get(f"/api/conversations/{conv}").json()["messages"]
        assert sum(m["role"] == "user" for m in messages) == 3

        # Other endpoints aren't limited.
        assert client.get("/api/health").status_code == 200

import json
import os

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select
from starlette.requests import Request

from app.db import make_engine
from app.main import create_app
from app.models import Provider, RateLimitBucket
from app.ratelimit import RateLimiter, client_ip
from tests.conftest import signup


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000_040.0  # 20s into the window starting at 1_000_020

    def __call__(self) -> float:
        return self.now


@pytest.fixture(params=["sqlite", "postgres"])
def engine(request):
    if request.param == "sqlite":
        engine = make_engine("sqlite://")
    else:
        url = os.environ.get("TEST_POSTGRES_URL")
        if not url:
            pytest.skip("set TEST_POSTGRES_URL to run against Postgres")
        engine = make_engine(url)
        SQLModel.metadata.drop_all(engine, tables=[RateLimitBucket.__table__])
    SQLModel.metadata.create_all(engine, tables=[RateLimitBucket.__table__])
    yield engine
    engine.dispose()


def test_limiter_allows_up_to_limit_then_blocks(engine) -> None:
    clock = FakeClock()
    limiter = RateLimiter(engine, 3, window=60, clock=clock)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    assert limiter.hit("a") == pytest.approx(40)  # window resets in 40s
    assert limiter.hit("b") is None  # other clients unaffected


def test_limiter_resets_next_window(engine) -> None:
    clock = FakeClock()
    limiter = RateLimiter(engine, 1, window=60, clock=clock)
    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None
    clock.now += 40  # next window
    assert limiter.hit("a") is None


def test_limiter_cleans_old_windows(engine, monkeypatch) -> None:
    clock = FakeClock()
    limiter = RateLimiter(engine, 5, window=60, clock=clock)
    limiter.hit("old")
    clock.now += 120
    monkeypatch.setattr("app.ratelimit.random.random", lambda: 0.0)
    limiter.hit("new")
    with Session(engine) as session:
        assert [r.key for r in session.exec(select(RateLimitBucket)).all()] == ["new"]


def test_limiter_shared_between_instances(engine) -> None:
    """Two limiters on one database act as one (separate serverless instances)."""
    clock = FakeClock()
    a = RateLimiter(engine, 2, window=60, clock=clock)
    b = RateLimiter(engine, 2, window=60, clock=clock)
    assert a.hit("ip") is None
    assert b.hit("ip") is None
    assert a.hit("ip") is not None


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
        signup(client, "admin@example.com")
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

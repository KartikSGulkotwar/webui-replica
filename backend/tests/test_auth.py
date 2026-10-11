import time

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, select

from app.auth import SESSION_COOKIE
from app.main import create_app
from app.models import Conversation, User
from app.security import session_secret
from tests.conftest import PASSWORD, signup


def test_first_signup_becomes_admin_and_is_signed_in(anon_client) -> None:
    assert anon_client.get("/api/auth/me").status_code == 401
    assert anon_client.get("/api/config").json()["has_users"] is False

    user = signup(anon_client, "  Founder@Example.COM ", "Founder")

    assert user["role"] == "admin" and user["email"] == "founder@example.com"
    assert "password" not in str(user).lower().replace("has_password", "")
    assert anon_client.get("/api/auth/me").json()["id"] == user["id"]
    assert anon_client.get("/api/config").json()["has_users"] is True


def test_session_cookie_flags(anon_client) -> None:
    resp = anon_client.post(
        "/api/auth/signup", json={"name": "A", "email": "a@example.com", "password": PASSWORD}
    )
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    https = anon_client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": PASSWORD},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert "Secure" in https.headers["set-cookie"]


def test_later_signups_get_default_role(client, app) -> None:
    with TestClient(app) as other:
        assert signup(other, "new@example.com")["role"] == "pending"
        # Pending users are signed in but can't use the app yet.
        assert other.get("/api/auth/me").status_code == 200
        assert other.get("/api/conversations").status_code == 403
        assert other.get("/api/models").status_code == 403


def test_duplicate_email(client, app) -> None:
    with TestClient(app) as other:
        resp = other.post(
            "/api/auth/signup",
            json={"name": "X", "email": "ADMIN@example.com", "password": PASSWORD},
        )
        assert resp.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"name": "X", "email": "not-an-email", "password": PASSWORD},
        {"name": "X", "email": "x@example.com", "password": "short"},
        {"name": "   ", "email": "x@example.com", "password": PASSWORD},
    ],
)
def test_signup_validation(anon_client, body) -> None:
    assert anon_client.post("/api/auth/signup", json=body).status_code == 422


def test_login_logout(client, app) -> None:
    with TestClient(app) as fresh:
        bad = fresh.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
        assert bad.status_code == 401 and bad.json()["detail"] == "Incorrect email or password"
        unknown = fresh.post(
            "/api/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
        )
        assert unknown.status_code == 401  # same message: doesn't reveal which emails exist
        assert unknown.json()["detail"] == bad.json()["detail"]

        ok = fresh.post(
            "/api/auth/login", json={"email": " Admin@Example.com", "password": PASSWORD}
        )
        assert ok.status_code == 200 and ok.json()["role"] == "admin"
        assert fresh.get("/api/conversations").status_code == 200

        assert fresh.post("/api/auth/logout").status_code == 204
        assert fresh.get("/api/conversations").status_code == 401


def test_tampered_and_expired_tokens_are_rejected(client, app, settings) -> None:
    user_id = client.get("/api/auth/me").json()["id"]
    secret = session_secret(settings)
    now = int(time.time())
    forged = jwt.encode({"sub": user_id, "sv": 0, "exp": now + 60}, "wrong-secret", "HS256")
    expired = jwt.encode({"sub": user_id, "sv": 0, "exp": now - 1}, secret, "HS256")
    for token in (forged, expired, "garbage"):
        with TestClient(app) as c:
            c.cookies.set(SESSION_COOKIE, token)
            assert c.get("/api/auth/me").status_code == 401


def test_password_change_signs_out_other_sessions(client, app) -> None:
    with TestClient(app) as laptop:
        laptop.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
        assert laptop.get("/api/auth/me").status_code == 200

        wrong = client.patch(
            "/api/auth/me", json={"current_password": "nope", "new_password": "a-new-password"}
        )
        assert wrong.status_code == 400
        ok = client.patch(
            "/api/auth/me",
            json={"name": "Boss", "current_password": PASSWORD, "new_password": "a-new-password"},
        )
        assert ok.status_code == 200 and ok.json()["name"] == "Boss"

        assert client.get("/api/auth/me").status_code == 200  # this session got a new cookie
        assert laptop.get("/api/auth/me").status_code == 401  # the other one is signed out
        relogin = laptop.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": "a-new-password"}
        )
        assert relogin.status_code == 200


def test_first_admin_claims_chats_created_before_accounts(app, anon_client, session) -> None:
    session.add(Conversation(id="old1", title="Before accounts"))
    session.add(Conversation(id="old2", title="Anonymous browser", owner_id="anon-cookie-id"))
    session.commit()

    signup(anon_client, "first@example.com")

    titles = {c["title"] for c in anon_client.get("/api/conversations").json()}
    assert titles == {"Before accounts", "Anonymous browser"}


def test_guest_access(settings) -> None:
    settings.guest_access = True
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    with TestClient(app) as admin:
        signup(admin, "admin@example.com")
    with TestClient(app) as guest:
        assert guest.get("/api/config").json()["guest_access"] is True
        user = guest.post("/api/auth/guest").json()
        assert user["is_guest"] and user["role"] == "user" and user["email"] is None
        assert guest.post("/api/conversations", json={}).status_code == 201
        # Calling it again keeps the same guest instead of making another.
        assert guest.post("/api/auth/guest").json()["id"] == user["id"]
        assert guest.patch("/api/auth/me", json={"name": "x"}).status_code == 403


def test_guest_access_disabled_by_default(anon_client) -> None:
    assert anon_client.post("/api/auth/guest").status_code == 403


def test_auth_endpoints_are_rate_limited(settings) -> None:
    settings.auth_rate_limit_per_minute = 3
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    with TestClient(app) as c:
        body = {"email": "x@example.com", "password": "wrong-password"}
        assert [c.post("/api/auth/login", json=body).status_code for _ in range(3)] == [401] * 3
        blocked = c.post("/api/auth/login", json=body)
        assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_passwords_are_hashed(client, session) -> None:
    user = session.exec(select(User).where(User.email == "admin@example.com")).one()
    assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash

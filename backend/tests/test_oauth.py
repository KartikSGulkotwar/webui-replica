from urllib.parse import parse_qs, urlsplit

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from app.main import create_app
from app.models import OAuthAccount, User
from app.routers.auth import OAUTH_STATE_COOKIE
from tests.conftest import signup

GH_TOKEN = "https://github.com/login/oauth/access_token"
GH_USER = "https://api.github.com/user"
GH_EMAILS = "https://api.github.com/user/emails"


@pytest.fixture
def oauth_app(settings):
    # A copy, so the shared settings (used by anon_client) stay without OAuth.
    oauth_settings = settings.model_copy(
        update={
            "github_client_id": "gh-id",
            "github_client_secret": "gh-secret",
            "google_client_id": "g-id",
            "google_client_secret": "g-secret",
            "public_url": "https://demo.example",
        }
    )
    app = create_app(oauth_settings)
    SQLModel.metadata.create_all(app.state.engine)
    return app


def start(client: TestClient, provider: str = "github") -> str:
    resp = client.get(f"/api/auth/oauth/{provider}/login", follow_redirects=False)
    assert resp.status_code == 303
    params = parse_qs(urlsplit(resp.headers["location"]).query)
    assert params["redirect_uri"] == [f"https://demo.example/api/auth/oauth/{provider}/callback"]
    return params["state"][0]


def mock_github(email="dev@example.com", verified=True, user_id=42):
    respx.post(GH_TOKEN).respond(json={"access_token": "gho_x"})
    respx.get(GH_USER).respond(json={"id": user_id, "login": "devcat", "name": "Dev Cat"})
    respx.get(GH_EMAILS).respond(json=[{"email": email, "primary": True, "verified": verified}])


def test_config_lists_configured_providers(oauth_app, anon_client) -> None:
    with TestClient(oauth_app) as c:
        assert c.get("/api/config").json()["oauth_providers"] == ["github", "google"]
    assert anon_client.get("/api/config").json()["oauth_providers"] == []
    assert anon_client.get("/api/auth/oauth/github/login").status_code == 404


def test_login_redirect_sets_state_cookie(oauth_app) -> None:
    with TestClient(oauth_app) as c:
        resp = c.get("/api/auth/oauth/github/login", follow_redirects=False)
        location = resp.headers["location"]
        assert location.startswith("https://github.com/login/oauth/authorize?")
        assert "client_id=gh-id" in location and "scope=read%3Auser+user%3Aemail" in location
        assert OAUTH_STATE_COOKIE in resp.headers["set-cookie"]
        assert "HttpOnly" in resp.headers["set-cookie"]


@respx.mock
def test_github_signup_creates_first_admin(oauth_app) -> None:
    mock_github()
    with TestClient(oauth_app) as c:
        state = start(c)
        resp = c.get(
            f"/api/auth/oauth/github/callback?code=abc&state={state}", follow_redirects=False
        )
        assert resp.status_code == 303 and resp.headers["location"] == "/"
        me = c.get("/api/auth/me").json()
        assert me["email"] == "dev@example.com" and me["name"] == "Dev Cat"
        assert me["role"] == "admin" and me["has_password"] is False
    token_call = respx.calls[0].request
    assert b"client_secret=gh-secret" in token_call.content and b"code=abc" in token_call.content


@respx.mock
def test_github_links_existing_account_by_verified_email(oauth_app) -> None:
    mock_github(email="admin@example.com")
    with TestClient(oauth_app) as c:
        existing = signup(c, "admin@example.com")
        c.post("/api/auth/logout")
        state = start(c)
        c.get(f"/api/auth/oauth/github/callback?code=abc&state={state}", follow_redirects=False)
        assert c.get("/api/auth/me").json()["id"] == existing["id"]
    with Session(oauth_app.state.engine) as s:
        link = s.exec(select(OAuthAccount)).one()
        assert (link.provider, link.subject, link.user_id) == ("github", "42", existing["id"])
        assert len(s.exec(select(User)).all()) == 1


@respx.mock
def test_state_mismatch_is_rejected(oauth_app) -> None:
    mock_github()
    with TestClient(oauth_app) as c:
        start(c)
        resp = c.get(
            "/api/auth/oauth/github/callback?code=abc&state=forged", follow_redirects=False
        )
        assert resp.status_code == 303 and resp.headers["location"].startswith("/auth?error=")
        assert c.get("/api/auth/me").status_code == 401
    assert not respx.calls  # never exchanged the code


@respx.mock
def test_unverified_github_email_is_rejected(oauth_app) -> None:
    mock_github(verified=False)
    with TestClient(oauth_app) as c:
        state = start(c)
        resp = c.get(
            f"/api/auth/oauth/github/callback?code=abc&state={state}", follow_redirects=False
        )
        assert (
            "no%20verified%20email" in resp.headers["location"]
            or "verified" in resp.headers["location"]
        )
        assert c.get("/api/auth/me").status_code == 401


@respx.mock
def test_signup_disabled_blocks_new_oauth_users(oauth_app) -> None:
    mock_github(email="stranger@example.com", user_id=7)
    with TestClient(oauth_app) as admin:
        signup(admin, "admin@example.com")
        admin.put("/api/admin/settings", json={"enable_signup": False, "default_user_role": "user"})
    with TestClient(oauth_app) as c:
        state = start(c)
        resp = c.get(
            f"/api/auth/oauth/github/callback?code=abc&state={state}", follow_redirects=False
        )
        assert "disabled" in resp.headers["location"]
        assert c.get("/api/auth/me").status_code == 401


@respx.mock
def test_google_flow(oauth_app) -> None:
    respx.post("https://oauth2.googleapis.com/token").respond(json={"access_token": "ya29"})
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").respond(
        json={"sub": "g-1", "email": "Gee@Example.com", "email_verified": True, "name": "Gee"}
    )
    with TestClient(oauth_app) as c:
        state = start(c, "google")
        c.get(f"/api/auth/oauth/google/callback?code=xyz&state={state}", follow_redirects=False)
        assert c.get("/api/auth/me").json()["email"] == "gee@example.com"


def test_cancelled_at_provider(oauth_app) -> None:
    with TestClient(oauth_app) as c:
        state = start(c)
        resp = c.get(
            f"/api/auth/oauth/github/callback?error=access_denied&state={state}",
            follow_redirects=False,
        )
        assert "cancelled" in resp.headers["location"]

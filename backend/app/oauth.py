"""Sign in with GitHub or Google (OAuth 2.0 authorization-code flow)."""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import Settings

TIMEOUT = httpx.Timeout(10.0)


class OAuthError(Exception):
    """Shown to the user on the sign-in page."""


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    name: str


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    scope: str
    client_id: str
    client_secret: str

    def authorize_redirect(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
            "response_type": "code",
        }
        if self.name == "google":
            params["prompt"] = "select_account"
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, http: httpx.AsyncClient, code: str, redirect_uri: str) -> str:
        resp = await http.post(
            self.token_url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        token = data.get("access_token")
        if resp.status_code >= 400 or not token:
            raise OAuthError(f"{self.label} sign-in failed: {data.get('error', resp.status_code)}")
        return token

    async def fetch_identity(self, http: httpx.AsyncClient, token: str) -> Identity:
        if self.name == "github":
            return await _github_identity(http, token)
        return await _google_identity(http, token)


async def _github_identity(http: httpx.AsyncClient, token: str) -> Identity:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    user = (await http.get("https://api.github.com/user", headers=headers, timeout=TIMEOUT)).json()
    emails = (
        await http.get("https://api.github.com/user/emails", headers=headers, timeout=TIMEOUT)
    ).json()
    verified = [e for e in emails if isinstance(e, dict) and e.get("verified")]
    primary = next((e for e in verified if e.get("primary")), verified[0] if verified else None)
    if primary is None:
        raise OAuthError("Your GitHub account has no verified email address")
    return Identity(
        subject=str(user["id"]),
        email=primary["email"].lower(),
        name=user.get("name") or user.get("login") or primary["email"].split("@")[0],
    )


async def _google_identity(http: httpx.AsyncClient, token: str) -> Identity:
    info = (
        await http.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
    ).json()
    if not info.get("email") or not info.get("email_verified"):
        raise OAuthError("Your Google account has no verified email address")
    return Identity(
        subject=str(info["sub"]),
        email=info["email"].lower(),
        name=info.get("name") or info["email"].split("@")[0],
    )


def configured_providers(settings: Settings) -> dict[str, OAuthProvider]:
    providers = {}
    if settings.github_client_id and settings.github_client_secret:
        providers["github"] = OAuthProvider(
            name="github",
            label="GitHub",
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            scope="read:user user:email",
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
        )
    if settings.google_client_id and settings.google_client_secret:
        providers["google"] = OAuthProvider(
            name="google",
            label="Google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scope="openid email profile",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
    return providers

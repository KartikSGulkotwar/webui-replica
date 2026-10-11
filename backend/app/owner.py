"""Anonymous per-browser ownership of conversations.

Every browser gets a random ID in an HttpOnly cookie. Conversations record the
ID that created them. With ISOLATE_CHATS_BY_BROWSER on (public demos, which have
no login), each browser only sees its own conversations; otherwise all are shared,
which suits a single-user self-hosted install.
"""

import re
import secrets
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Annotated

from fastapi import Depends, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

COOKIE = "webui_owner"
MAX_AGE = 60 * 60 * 24 * 365
VALID_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _cookie_value(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            jar = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:
                return None
            morsel = jar.get(COOKIE)
            if morsel and VALID_ID.match(morsel.value):
                return morsel.value
    return None


def _is_https(scope: Scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-proto":
            return value.decode("latin-1").split(",")[0].strip() == "https"
    return False


class OwnerCookieMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so streaming and client-disconnect
    detection for the Stop button keep working."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        owner_id = _cookie_value(scope)
        is_new = owner_id is None
        if owner_id is None:
            owner_id = secrets.token_urlsafe(24)
        scope.setdefault("state", {})["owner_id"] = owner_id

        async def send_with_cookie(message: Message) -> None:
            if is_new and message["type"] == "http.response.start":
                cookie = (
                    f"{COOKIE}={owner_id}; Path=/; Max-Age={MAX_AGE}; HttpOnly; SameSite=Lax"
                    + ("; Secure" if _is_https(scope) else "")
                )
                message["headers"] = [*message.get("headers", []), (b"set-cookie", cookie.encode())]
            await send(message)

        await self.app(scope, receive, send_with_cookie)


@dataclass(frozen=True)
class Owner:
    id: str
    # Owner to filter conversations by; None when conversations are shared.
    scope: str | None


def get_owner(request: Request) -> Owner:
    owner_id = request.state.owner_id
    isolate = request.app.state.settings.isolate_chats_by_browser
    return Owner(id=owner_id, scope=owner_id if isolate else None)


OwnerDep = Annotated[Owner, Depends(get_owner)]

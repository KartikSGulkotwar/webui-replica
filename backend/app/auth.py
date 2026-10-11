"""Session cookies and the dependencies that protect routes."""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlmodel import Session

from app.config import Settings
from app.db import SessionDep
from app.models import User, utcnow
from app.security import create_session_token, decode_session_token

SESSION_COOKIE = "webui_session"
# Don't write to the database on every request just to record activity.
ACTIVITY_INTERVAL = timedelta(minutes=5)


def is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return request.url.scheme == "https" or proto == "https"


def set_session_cookie(response: Response, request: Request, user: User) -> None:
    settings: Settings = request.app.state.settings
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id, user.session_version, settings),
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",  # not sent on cross-site POST/DELETE, which blocks CSRF
        secure=is_https(request),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_optional_user(request: Request, session: SessionDep) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    claims = decode_session_token(token, request.app.state.settings)
    if claims is None:
        return None
    user = session.get(User, claims["sub"])
    if user is None or user.session_version != claims["sv"]:
        return None
    _touch(session, user)
    return user


def _touch(session: Session, user: User) -> None:
    now = utcnow()
    last = user.last_active_at
    if last.tzinfo is None:  # SQLite returns naive datetimes
        last = last.replace(tzinfo=now.tzinfo)
    if now - last > ACTIVITY_INTERVAL:
        user.last_active_at = now
        session.add(user)
        session.commit()
        session.refresh(user)


OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]


def get_current_user(user: OptionalUserDep) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_active_user(user: CurrentUserDep) -> User:
    """Signed in and approved (not pending)."""
    if user.role == "pending":
        raise HTTPException(status_code=403, detail="Your account is waiting for approval")
    return user


ActiveUserDep = Annotated[User, Depends(get_active_user)]


def get_admin_user(user: ActiveUserDep) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user


AdminUserDep = Annotated[User, Depends(get_admin_user)]

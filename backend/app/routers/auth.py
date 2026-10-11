import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, or_, select, update

from app.app_settings import get_admin_settings
from app.auth import (
    CurrentUserDep,
    OptionalUserDep,
    clear_session_cookie,
    is_https,
    set_session_cookie,
)
from app.db import SessionDep
from app.models import Conversation, OAuthAccount, User
from app.oauth import OAuthError, configured_providers
from app.ratelimit import client_ip
from app.schemas import LoginRequest, ProfileUpdate, SignupRequest, UserRead
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "webui_oauth_state"


def to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,  # type: ignore[arg-type]
        is_guest=user.is_guest,
        has_password=user.password_hash is not None,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
    )


def limit_auth(request: Request) -> None:
    """Throttle password guessing and mass account creation per IP."""
    limiter = request.app.state.auth_limiter
    if limiter is None:
        return
    ip = client_ip(request, request.app.state.settings.trusted_proxy_hops)
    retry = limiter.hit(f"auth:{ip}")
    if retry is not None:
        seconds = max(1, int(retry) + 1)
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Please wait {seconds} seconds and try again.",
            headers={"Retry-After": str(seconds)},
        )


AuthLimited = Depends(limit_auth)


def has_real_users(session: Session) -> bool:
    stmt = select(func.count()).select_from(User).where(col(User.is_guest).is_(False))
    return session.exec(stmt).one() > 0


def claim_orphan_conversations(session: Session, admin: User) -> None:
    """Give the first admin the conversations created before accounts existed."""
    user_ids = select(User.id)
    session.exec(
        update(Conversation)
        .where(
            or_(col(Conversation.owner_id).is_(None), col(Conversation.owner_id).not_in(user_ids))
        )
        .values(owner_id=admin.id)
    )


def role_for_new_user(session: Session, request: Request) -> str:
    """First real account becomes admin; after that, sign-up must be enabled."""
    if not has_real_users(session):
        return "admin"
    admin_settings = get_admin_settings(session, request.app.state.settings)
    if not admin_settings.enable_signup:
        raise HTTPException(status_code=403, detail="Sign-up is disabled on this site")
    return admin_settings.default_user_role


def create_user(session: Session, user: User) -> User:
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from exc
    if user.role == "admin" and not has_other_admins(session, user):
        claim_orphan_conversations(session, user)
    session.commit()
    session.refresh(user)
    return user


def has_other_admins(session: Session, user: User) -> bool:
    stmt = select(func.count()).select_from(User).where(User.role == "admin", User.id != user.id)
    return session.exec(stmt).one() > 0


@router.post(
    "/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AuthLimited],
)
def signup(body: SignupRequest, request: Request, response: Response, session: SessionDep):
    if session.exec(select(User).where(User.email == body.email)).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = create_user(
        session,
        User(
            email=body.email,
            name=body.name,
            password_hash=hash_password(body.password),
            role=role_for_new_user(session, request),
        ),
    )
    set_session_cookie(response, request, user)
    return to_read(user)


@router.post("/login", response_model=UserRead, dependencies=[AuthLimited])
def login(body: LoginRequest, request: Request, response: Response, session: SessionDep):
    user = session.exec(select(User).where(User.email == body.email.strip().lower())).first()
    # verify_password runs even for unknown emails, so timing doesn't reveal accounts.
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    set_session_cookie(response, request, user)
    return to_read(user)


@router.post("/guest", response_model=UserRead, dependencies=[AuthLimited])
def guest(request: Request, response: Response, session: SessionDep, current: OptionalUserDep):
    if not request.app.state.settings.guest_access:
        raise HTTPException(status_code=403, detail="Guest access is disabled on this site")
    if current is not None:
        return to_read(current)
    user = create_user(session, User(name="Guest", role="user", is_guest=True))
    set_session_cookie(response, request, user)
    return to_read(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=UserRead)
def me(user: CurrentUserDep) -> UserRead:
    return to_read(user)


@router.patch("/me", response_model=UserRead)
def update_me(
    body: ProfileUpdate,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUserDep,
) -> UserRead:
    if user.is_guest:
        raise HTTPException(status_code=403, detail="Guest accounts can't be edited")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be blank")
        user.name = name
    if body.new_password is not None:
        # Accounts created with GitHub/Google have no password yet and may set one.
        if user.password_hash is not None and not verify_password(
            user.password_hash, body.current_password or ""
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.password_hash = hash_password(body.new_password)
        user.session_version += 1  # sign out other devices
    session.add(user)
    session.commit()
    session.refresh(user)
    set_session_cookie(response, request, user)
    return to_read(user)


# --- OAuth ---------------------------------------------------------------------


def public_base(request: Request) -> str:
    configured = request.app.state.settings.public_url.rstrip("/")
    if configured:
        return configured
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{'https' if is_https(request) else 'http'}://{host}"


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]


def oauth_error(message: str) -> RedirectResponse:
    response = RedirectResponse(f"/auth?error={message}", status_code=303)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


@router.get("/oauth/{name}/login")
def oauth_login(name: str, request: Request) -> RedirectResponse:
    provider = configured_providers(request.app.state.settings).get(name)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown sign-in provider")
    state = secrets.token_urlsafe(24)
    redirect_uri = f"{public_base(request)}/api/auth/oauth/{name}/callback"
    response = RedirectResponse(provider.authorize_redirect(redirect_uri, state), status_code=303)
    # The provider sends the browser back with this state; a mismatch means the
    # callback wasn't started by this browser (login CSRF).
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        f"{name}:{state}",
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=is_https(request),
        path="/",
    )
    return response


@router.get("/oauth/{name}/callback")
async def oauth_callback(
    name: str,
    request: Request,
    session: SessionDep,
    http: HttpDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    provider = configured_providers(request.app.state.settings).get(name)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown sign-in provider")
    expected = request.cookies.get(OAUTH_STATE_COOKIE, "")
    if error:
        return oauth_error("Sign-in was cancelled")
    if not code or not state or not secrets.compare_digest(expected, f"{name}:{state}"):
        return oauth_error("Sign-in expired. Please try again.")

    try:
        token = await provider.exchange_code(
            http, code, f"{public_base(request)}/api/auth/oauth/{name}/callback"
        )
        identity = await provider.fetch_identity(http, token)
    except OAuthError as exc:
        return oauth_error(str(exc))
    except (httpx.HTTPError, ValueError, KeyError):
        return oauth_error(f"Couldn't reach {provider.label}. Please try again.")

    link = session.get(OAuthAccount, (name, identity.subject))
    user = session.get(User, link.user_id) if link else None
    if user is None:
        # The provider verified this email, so it's safe to link an existing account.
        user = session.exec(select(User).where(User.email == identity.email)).first()
    if user is None:
        try:
            role = role_for_new_user(session, request)
        except HTTPException as exc:
            return oauth_error(exc.detail)
        user = create_user(session, User(email=identity.email, name=identity.name, role=role))
    if link is None:
        session.add(OAuthAccount(provider=name, subject=identity.subject, user_id=user.id))
        session.commit()

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    set_session_cookie(response, request, user)
    return response

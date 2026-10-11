from pathlib import Path

from fastapi import APIRouter, Request
from sqlmodel import Session

from app import __version__
from app.app_settings import get_admin_settings
from app.oauth import configured_providers
from app.routers.auth import has_real_users
from app.schemas import AppConfig

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/config", response_model=AppConfig)
def config(request: Request) -> AppConfig:
    settings = request.app.state.settings
    with Session(request.app.state.engine) as session:
        has_users = has_real_users(session)
        admin_settings = get_admin_settings(session, settings)
    return AppConfig(
        encryption_configured=request.app.state.cipher.configured,
        in_docker=Path("/.dockerenv").exists(),
        default_model=settings.default_model or None,
        has_users=has_users,
        # Before the first account exists, sign-up is always open (it creates the admin).
        signup_enabled=admin_settings.enable_signup or not has_users,
        guest_access=settings.guest_access,
        oauth_providers=list(configured_providers(settings)),
    )

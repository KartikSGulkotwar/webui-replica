from pathlib import Path

from fastapi import APIRouter, Request
from sqlmodel import Session

from app import __version__
from app.app_settings import get_admin_settings, usable_tools
from app.auth import ActiveUserDep
from app.images.service import image_config
from app.oauth import configured_providers
from app.routers.auth import has_real_users
from app.schemas import AppConfig, ToolInfo
from app.tools.registry import TOOLS
from app.websearch.service import web_search_config

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
        search = web_search_config(session, settings, request.app.state.cipher)
        images = image_config(session, settings, request.app.state.cipher)
    return AppConfig(
        encryption_configured=request.app.state.cipher.configured,
        in_docker=Path("/.dockerenv").exists(),
        default_model=settings.default_model or None,
        has_users=has_users,
        # Before the first account exists, sign-up is always open (it creates the admin).
        signup_enabled=admin_settings.enable_signup or not has_users,
        guest_access=settings.guest_access,
        oauth_providers=list(configured_providers(settings)),
        max_upload_mb=settings.max_upload_mb,
        web_search=search.enabled,
        image_generation=images.enabled,
    )


@router.get("/tools", response_model=list[ToolInfo])
def list_tools(request: Request, user: ActiveUserDep, all: bool = False) -> list[ToolInfo]:
    """Tools an admin has enabled, for the tools menu in chat.

    Admins can pass ?all=true to list every built-in tool (for the settings page).
    """
    with Session(request.app.state.engine) as session:
        tools = (
            list(TOOLS.values())
            if all and user.role == "admin"
            else usable_tools(session, request.app.state.settings, request.app.state.cipher)
        )
    return [ToolInfo(id=t.id, label=t.label, emoji=t.emoji, summary=t.summary) for t in tools]

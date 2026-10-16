import hmac
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlmodel import Session

from app import __version__
from app.app_settings import get_admin_settings, usable_tools
from app.audio import audio_config
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
    """Liveness: the process is up."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready(request: Request) -> Response:
    """Readiness: the database answers. Load balancers stop sending traffic
    while this fails."""
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    return JSONResponse({"status": "ready", "database": "up"})


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    """Prometheus metrics, for scrapers holding METRICS_TOKEN. Each process keeps
    its own counters; scrape every replica (Kubernetes does this per pod)."""
    token = request.app.state.settings.metrics_token
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    if not hmac.compare_digest(given, token):
        raise HTTPException(status_code=401, detail="Invalid metrics token")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/config", response_model=AppConfig)
def config(request: Request) -> AppConfig:
    settings = request.app.state.settings
    with Session(request.app.state.engine) as session:
        has_users = has_real_users(session)
        admin_settings = get_admin_settings(session, settings)
        search = web_search_config(session, settings, request.app.state.cipher)
        images = image_config(session, settings, request.app.state.cipher)
        stt, tts = audio_config(session, settings, request.app.state.cipher)
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
        speech_to_text=stt.enabled,
        text_to_speech=tts.enabled,
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

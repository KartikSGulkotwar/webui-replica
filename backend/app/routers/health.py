from pathlib import Path

from fastapi import APIRouter, Request

from app import __version__
from app.schemas import AppConfig

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/config", response_model=AppConfig)
async def config(request: Request) -> AppConfig:
    return AppConfig(
        providers_read_only=request.app.state.settings.providers_read_only,
        encryption_configured=request.app.state.cipher.configured,
        in_docker=Path("/.dockerenv").exists(),
    )

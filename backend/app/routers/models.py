from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app.app_settings import get_admin_settings
from app.auth import ActiveUserDep
from app.catalog import build_catalog
from app.db import SessionDep
from app.providers.registry import RegistryDep
from app.schemas import ModelsResponse

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    request: Request, session: SessionDep, registry: RegistryDep, user: ActiveUserDep
) -> ModelsResponse:
    await run_in_threadpool(registry.sync, session)
    arena = get_admin_settings(session, request.app.state.settings).arena_models or []
    return await build_catalog(session, registry, user, arena)

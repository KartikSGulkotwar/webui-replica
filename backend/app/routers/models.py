from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.auth import ActiveUserDep
from app.catalog import build_catalog
from app.db import SessionDep
from app.providers.registry import RegistryDep
from app.schemas import ModelsResponse

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    session: SessionDep, registry: RegistryDep, user: ActiveUserDep
) -> ModelsResponse:
    await run_in_threadpool(registry.sync, session)
    return await build_catalog(session, registry, user)

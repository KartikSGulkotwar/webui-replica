import asyncio
import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.auth import ActiveUserDep
from app.db import SessionDep
from app.providers.base import ProviderError
from app.providers.registry import RegistryDep, RegistryEntry
from app.schemas import ModelInfo, ModelsResponse, ProviderStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["models"])


async def _fetch(entry: RegistryEntry) -> list[ModelInfo]:
    if entry.provider is None:
        raise ProviderError(entry.error or "Provider unavailable")
    return await entry.provider.list_models()


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    session: SessionDep, registry: RegistryDep, user: ActiveUserDep
) -> ModelsResponse:
    await run_in_threadpool(registry.sync, session)
    entries = registry.entries()
    # One slow or broken provider must not hide the others' models.
    results = await asyncio.gather(*(_fetch(e) for e in entries), return_exceptions=True)

    models: list[ModelInfo] = []
    statuses: list[ProviderStatus] = []
    for entry, result in zip(entries, results, strict=True):
        if isinstance(result, BaseException):
            if isinstance(result, ProviderError):
                error = str(result)
            else:
                logger.exception(
                    "Unexpected error listing models for %s", entry.id, exc_info=result
                )
                error = "Unexpected error"
            statuses.append(
                ProviderStatus(id=entry.id, name=entry.name, kind=entry.kind, ok=False, error=error)
            )
            continue
        models.extend(result)
        statuses.append(ProviderStatus(id=entry.id, name=entry.name, kind=entry.kind, ok=True))

    statuses.sort(key=lambda s: s.name.lower())
    models.sort(key=lambda m: (m.provider_name.lower(), m.name.lower()))
    return ModelsResponse(models=models, providers=statuses)

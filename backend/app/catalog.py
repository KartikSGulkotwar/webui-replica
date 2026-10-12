"""The model menu: provider models (minus hidden ones) plus custom models."""

import asyncio
import json
import logging
from dataclasses import dataclass

from fastapi import HTTPException
from sqlmodel import Session, col, or_, select

from app.models import CustomModel, ModelSetting, User
from app.providers.base import ProviderError, split_model_id
from app.providers.registry import ProviderRegistry, RegistryEntry
from app.schemas import ModelInfo, ModelsResponse, ProviderStatus

logger = logging.getLogger(__name__)

PERSONA = "persona"  # provider ID prefix of custom models: "persona:{id}"
CUSTOM_GROUP = ProviderStatus(id=PERSONA, name="Custom models", kind="custom", ok=True)


async def _fetch(entry: RegistryEntry) -> list[ModelInfo]:
    if entry.provider is None:
        raise ProviderError(entry.error or "Provider unavailable")
    return await entry.provider.list_models()


async def provider_models(
    registry: ProviderRegistry,
) -> tuple[list[ModelInfo], list[ProviderStatus]]:
    """Every model from every enabled provider, with per-provider status."""
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
    return models, statuses


def model_settings(session: Session) -> dict[str, ModelSetting]:
    return {s.model_id: s for s in session.exec(select(ModelSetting))}


def hidden_model_ids(session: Session) -> set[str]:
    stmt = select(ModelSetting.model_id).where(col(ModelSetting.hidden).is_(True))
    return set(session.exec(stmt))


def visible_custom_models(session: Session, user: User) -> list[CustomModel]:
    """The user's own custom models plus everyone's public ones."""
    stmt = (
        select(CustomModel)
        .where(or_(CustomModel.owner_id == user.id, CustomModel.visibility == "public"))
        .order_by(col(CustomModel.name))
    )
    return list(session.exec(stmt))


def custom_model_info(c: CustomModel) -> ModelInfo:
    return ModelInfo(
        id=f"{PERSONA}:{c.id}",
        name=c.name,
        provider_id=PERSONA,
        provider_name="Custom",
        provider_kind="custom",
        description=c.description or None,
        emoji=c.emoji,
        base_model_id=c.base_model_id,
    )


async def build_catalog(session: Session, registry: ProviderRegistry, user: User) -> ModelsResponse:
    models, statuses = await provider_models(registry)
    available = {m.id for m in models}
    settings = model_settings(session)
    shown: list[ModelInfo] = []
    for m in models:
        s = settings.get(m.id)
        if s and s.hidden:
            continue
        if s and s.display_name:
            m = m.model_copy(update={"name": s.display_name})
        shown.append(m)
    # A custom model whose base model is gone (provider down, model removed)
    # can't answer, so leave it out until it's back.
    customs = [
        custom_model_info(c)
        for c in visible_custom_models(session, user)
        if c.base_model_id in available
    ]
    # A working provider whose models are all hidden would be an empty group in
    # the menu; drop it. (Providers that are down or have no models still show,
    # so their status and hints stay visible.)
    listed = {m.provider_id for m in models}
    shown_providers = {m.provider_id for m in shown}
    statuses = [
        s for s in statuses if not (s.ok and s.id in listed and s.id not in shown_providers)
    ]
    statuses.sort(key=lambda s: s.name.lower())
    shown.sort(key=lambda m: (m.provider_name.lower(), m.name.lower()))
    if customs:
        statuses.insert(0, CUSTOM_GROUP)
    return ModelsResponse(models=customs + shown, providers=statuses)


@dataclass(frozen=True)
class ResolvedModel:
    provider_id: str
    model: str
    persona: CustomModel | None = None

    @property
    def knowledge_ids(self) -> list[str]:
        return json.loads(self.persona.knowledge_json) if self.persona else []


def resolve_model(session: Session, user: User, model_id: str) -> ResolvedModel:
    """Map a model ID from the menu to the provider model that will answer.

    Raises 422 for a malformed ID and 400 when the user may not use it.
    """
    try:
        provider_id, model = split_model_id(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if provider_id != PERSONA:
        if model_id in hidden_model_ids(session) and user.role != "admin":
            raise HTTPException(status_code=400, detail="This model isn't available")
        return ResolvedModel(provider_id, model)
    persona = session.get(CustomModel, model)
    if persona is None or (persona.owner_id != user.id and persona.visibility != "public"):
        raise HTTPException(status_code=400, detail="This custom model isn't available")
    base_provider, base_model = split_model_id(persona.base_model_id)
    return ResolvedModel(base_provider, base_model, persona)

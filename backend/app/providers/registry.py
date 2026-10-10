import logging
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlmodel import Session, select

from app.crypto import EncryptionError, KeyCipher
from app.models import Provider
from app.providers.base import BaseProvider, ProviderError
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.schemas import ProviderKind

logger = logging.getLogger(__name__)

PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "ollama": OllamaProvider,
    "openai_compat": OpenAICompatProvider,
}


def build_provider(row: Provider, client: httpx.AsyncClient, cipher: KeyCipher) -> BaseProvider:
    cls = PROVIDER_CLASSES.get(row.kind)
    if cls is None:
        raise ProviderError(f"Unknown provider kind {row.kind!r}")
    try:
        api_key = cipher.decrypt(row.api_key_encrypted) if row.api_key_encrypted else None
    except EncryptionError as exc:
        raise ProviderError(str(exc)) from exc
    return cls(id=row.id, name=row.name, base_url=row.base_url, client=client, api_key=api_key)


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    name: str
    kind: ProviderKind
    provider: BaseProvider | None  # None when it could not be built
    error: str | None = None


class ProviderRegistry:
    """Instances for the enabled providers in the database.

    Call sync() at the start of a request to pick up DB changes; instances are
    rebuilt only when their row changed, so the shared HTTP client is reused.
    """

    def __init__(self, client: httpx.AsyncClient, cipher: KeyCipher) -> None:
        self._client = client
        self._cipher = cipher
        self._entries: dict[str, tuple[tuple, RegistryEntry]] = {}

    def sync(self, session: Session) -> None:
        rows = session.exec(select(Provider).where(Provider.enabled == True)).all()  # noqa: E712
        fresh: dict[str, tuple[tuple, RegistryEntry]] = {}
        for row in rows:
            fingerprint = (row.kind, row.name, row.base_url, row.api_key_encrypted)
            cached = self._entries.get(row.id)
            if cached and cached[0] == fingerprint:
                fresh[row.id] = cached
                continue
            try:
                provider = build_provider(row, self._client, self._cipher)
                entry = RegistryEntry(row.id, row.name, row.kind, provider)
            except ProviderError as exc:
                logger.warning("Provider %s unavailable: %s", row.id, exc)
                entry = RegistryEntry(row.id, row.name, row.kind, None, str(exc))
            fresh[row.id] = (fingerprint, entry)
        self._entries = fresh

    def entries(self) -> list[RegistryEntry]:
        return [entry for _, entry in self._entries.values()]

    def get(self, provider_id: str) -> BaseProvider:
        cached = self._entries.get(provider_id)
        if cached is None:
            raise ProviderError(f"Provider {provider_id!r} not found or disabled")
        entry = cached[1]
        if entry.provider is None:
            raise ProviderError(entry.error or f"Provider {provider_id!r} unavailable")
        return entry.provider


def get_registry(request: Request) -> ProviderRegistry:
    return request.app.state.registry


RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]

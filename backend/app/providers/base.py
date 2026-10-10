import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar

import httpx

from app.schemas import (
    ChatMessage,
    ChatParams,
    ModelInfo,
    ProviderHealth,
    ProviderKind,
    StreamChunk,
)

# Listing models should be quick; streaming may sit idle while a large model loads.
LIST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
STREAM_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


class ProviderError(Exception):
    """A provider call failed. The message is safe to show to users."""


def split_model_id(model_id: str) -> tuple[str, str]:
    """Split "provider:model" on the first colon. Model names may contain colons
    (Ollama tags like "llama3.2:1b"); provider IDs never do."""
    provider_id, sep, model = model_id.partition(":")
    if not sep or not provider_id or not model:
        raise ValueError(f"Invalid model id {model_id!r}; expected 'provider:model'")
    return provider_id, model


def describe_http_error(exc: Exception, base_url: str) -> str:
    if isinstance(exc, httpx.ConnectError):
        return f"Cannot connect to {base_url}"
    if isinstance(exc, httpx.TimeoutException):
        return f"Timed out talking to {base_url}"
    if isinstance(exc, httpx.HTTPError):
        return f"Request to {base_url} failed: {exc}"
    return str(exc)


def error_from_response(resp: httpx.Response, body: bytes | None = None) -> ProviderError:
    """Build a readable error from a non-2xx response, preferring the provider's message."""
    raw = body if body is not None else resp.content
    detail = raw.decode(errors="replace").strip()[:300]
    try:
        payload = json.loads(raw)
        err = payload.get("error", payload)
        if isinstance(err, dict):
            detail = str(err.get("message") or err)
        elif isinstance(err, str):
            detail = err
    except (ValueError, AttributeError):
        pass
    return ProviderError(f"HTTP {resp.status_code}: {detail or resp.reason_phrase}")


class BaseProvider(ABC):
    kind: ClassVar[ProviderKind]

    def __init__(
        self,
        id: str,
        name: str,
        base_url: str,
        client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    def stream_chat(
        self, model: str, messages: list[ChatMessage], params: ChatParams
    ) -> AsyncIterator[StreamChunk]:
        """Yield text deltas, then exactly one chunk with done=True (carrying usage
        when the provider reports it). Raises ProviderError on failure."""

    async def health(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            models = await self.list_models()
        except ProviderError as exc:
            return ProviderHealth(ok=False, error=str(exc))
        latency = int((time.perf_counter() - start) * 1000)
        return ProviderHealth(ok=True, latency_ms=latency, model_count=len(models))

    def _model_info(self, name: str) -> ModelInfo:
        return ModelInfo(
            id=f"{self.id}:{name}",
            name=name,
            provider_id=self.id,
            provider_name=self.name,
            provider_kind=self.kind,
        )

    async def _get_json(self, path: str, headers: dict[str, str] | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = await self._client.get(url, headers=headers, timeout=LIST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise ProviderError(describe_http_error(exc, self.base_url)) from exc
        if resp.status_code >= 400:
            raise error_from_response(resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"{url} did not return JSON") from exc

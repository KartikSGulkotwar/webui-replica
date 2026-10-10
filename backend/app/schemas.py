from typing import Any, Literal

from pydantic import BaseModel

ProviderKind = Literal["ollama", "openai_compat"]
Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class ChatParams(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None


class ModelInfo(BaseModel):
    id: str  # namespaced: "{provider_id}:{name}"
    name: str
    provider_id: str
    provider_name: str
    provider_kind: ProviderKind


class ProviderHealth(BaseModel):
    ok: bool
    latency_ms: int | None = None
    model_count: int | None = None
    error: str | None = None


class StreamChunk(BaseModel):
    """One normalized piece of a provider stream: text, or the final done marker."""

    delta: str = ""
    done: bool = False
    usage: dict[str, Any] | None = None


class ProviderStatus(BaseModel):
    id: str
    name: str
    kind: ProviderKind
    ok: bool
    error: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    providers: list[ProviderStatus]

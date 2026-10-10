from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

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


# --- conversations ---------------------------------------------------------


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationRead(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    id: int
    role: Role
    content: str
    model_id: str | None
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


# --- chat -------------------------------------------------------------------


class ChatStreamRequest(BaseModel):
    conversation_id: str
    model_id: str = Field(min_length=3, description='Namespaced, e.g. "ollama:llama3.2:1b"')
    message: str = Field(min_length=1, max_length=100_000)
    params: ChatParams = Field(default_factory=ChatParams)

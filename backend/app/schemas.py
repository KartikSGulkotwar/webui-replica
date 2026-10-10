from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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


# --- providers ----------------------------------------------------------------


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")
    if len(value) <= len("https://") or " " in value:
        raise ValueError("Base URL is not a valid URL")
    return value


class ProviderRead(BaseModel):
    id: str
    name: str
    kind: ProviderKind
    base_url: str
    enabled: bool
    has_key: bool
    created_at: datetime
    updated_at: datetime


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: ProviderKind
    base_url: str = Field(max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    enabled: bool = True

    _url = field_validator("base_url")(normalize_base_url)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank")
        return v


class ProviderUpdate(BaseModel):
    """Omitted fields are unchanged. api_key: omit or null to keep, "" to remove."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return None if v is None else normalize_base_url(v)


class ProviderTest(BaseModel):
    """Connection test for unsaved form values. When editing an existing provider,
    pass provider_id and omit api_key to test with the stored key."""

    kind: ProviderKind
    base_url: str = Field(max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    provider_id: str | None = None

    _url = field_validator("base_url")(normalize_base_url)


class AppConfig(BaseModel):
    providers_read_only: bool
    encryption_configured: bool

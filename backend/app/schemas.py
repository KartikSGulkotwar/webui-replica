from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProviderKind = Literal["ollama", "openai_compat", "anthropic"]
Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class ChatParams(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None


# Kinds in the model menu: real providers, plus "custom" for saved assistants.
CatalogKind = Literal["ollama", "openai_compat", "anthropic", "custom"]


class ModelInfo(BaseModel):
    id: str  # namespaced: "{provider_id}:{name}"
    name: str
    provider_id: str
    provider_name: str
    provider_kind: CatalogKind
    # Custom models only:
    description: str | None = None
    emoji: str | None = None
    base_model_id: str | None = None


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
    # On the done chunk: the model that actually answered, when it differs from
    # the one requested (e.g. a server-side refusal fallback).
    served_by: str | None = None


class ProviderStatus(BaseModel):
    id: str
    name: str
    kind: CatalogKind
    ok: bool
    error: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    providers: list[ProviderStatus]


# --- conversations ---------------------------------------------------------


class AttachmentRefs(BaseModel):
    collection_ids: list[str] = Field(default_factory=list, max_length=20)
    document_ids: list[str] = Field(default_factory=list, max_length=50)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    system_prompt: str | None = Field(default=None, max_length=10_000)
    attachments: AttachmentRefs | None = None


class ConversationUpdate(BaseModel):
    """Omitted fields are unchanged. system_prompt "" clears it."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, max_length=10_000)
    pinned: bool | None = None
    archived: bool | None = None


class ConversationRead(BaseModel):
    id: str
    title: str
    pinned: bool
    archived: bool
    shared: bool = False
    # Search results only: an excerpt of the first message that matched.
    snippet: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    id: int
    role: Role
    content: str
    model_id: str | None
    rating: Literal[1, -1] | None = None
    rating_comment: str | None = None
    sources: list["SourceRead"] | None = None
    created_at: datetime


class SourceRead(BaseModel):
    n: int
    document_id: str
    filename: str
    page: int | None
    text: str


class AttachmentRead(BaseModel):
    kind: Literal["collection", "document"]
    id: str
    name: str


class ConversationDetail(ConversationRead):
    system_prompt: str | None
    share_id: str | None = None
    attachments: list[AttachmentRead] = Field(default_factory=list)
    messages: list[MessageRead]


class RatingUpdate(BaseModel):
    rating: Literal[1, -1] | None
    comment: str | None = Field(default=None, max_length=1000)


class ShareRead(BaseModel):
    share_id: str
    created_at: datetime
    updated_at: datetime


class SharedMessage(BaseModel):
    role: Role
    content: str
    model_id: str | None


class SharedChatRead(BaseModel):
    title: str
    messages: list[SharedMessage]
    updated_at: datetime


# --- chat -------------------------------------------------------------------


class ChatStreamRequest(BaseModel):
    """send: add `message` and reply. regenerate: replace the last reply.
    edit: change user message `message_id` to `message`, drop everything after it, reply."""

    conversation_id: str
    model_id: str = Field(min_length=3, description='Namespaced, e.g. "ollama:llama3.2:1b"')
    action: Literal["send", "regenerate", "edit"] = "send"
    message: str | None = Field(default=None, min_length=1, max_length=100_000)
    message_id: int | None = None
    params: ChatParams = Field(default_factory=ChatParams)

    @model_validator(mode="after")
    def _check_action(self) -> "ChatStreamRequest":
        if self.action in ("send", "edit") and not self.message:
            raise ValueError(f"'message' is required for {self.action}")
        if self.action == "edit" and self.message_id is None:
            raise ValueError("'message_id' is required for edit")
        return self


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
    encryption_configured: bool
    # Lets the UI suggest URLs that work from inside a container.
    in_docker: bool
    default_model: str | None
    # Sign-in page: no accounts yet means the next sign-up becomes the admin.
    has_users: bool
    signup_enabled: bool
    guest_access: bool
    oauth_providers: list[str]
    max_upload_mb: int


# --- accounts -----------------------------------------------------------------

UserRole = Literal["admin", "user", "pending"]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserRead(BaseModel):
    id: str
    email: str | None
    name: str
    role: UserRole
    is_guest: bool
    has_password: bool
    created_at: datetime
    last_active_at: datetime


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank")
        return v

    # "before" so pasted spaces are trimmed ahead of the format check.
    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    current_password: str | None = Field(default=None, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class AdminUserUpdate(BaseModel):
    role: UserRole


class AdminSettings(BaseModel):
    enable_signup: bool
    default_user_role: Literal["user", "pending"]


# --- knowledge (RAG) ---------------------------------------------------------------


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class DocumentRead(BaseModel):
    id: str
    collection_id: str | None
    filename: str
    size_bytes: int
    page_count: int | None
    chunk_count: int
    warning: str | None
    created_at: datetime


class CollectionRead(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: datetime
    updated_at: datetime


class CollectionDetail(CollectionRead):
    documents: list[DocumentRead]


class EmbeddingSettingsRead(BaseModel):
    engine: Literal["", "ollama", "openai"]
    base_url: str
    model: str
    has_key: bool
    # Chunks embedded with the current model vs. all chunks (for re-index hints).
    embedded_chunks: int
    total_chunks: int


class EmbeddingSettingsUpdate(BaseModel):
    engine: Literal["", "ollama", "openai"]
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    # Omit/null to keep the stored key, "" to remove it.
    api_key: str | None = Field(default=None, max_length=1000)


# --- model management ----------------------------------------------------------------


class AdminModelRead(BaseModel):
    id: str
    name: str  # the provider's own model name
    display_name: str | None
    hidden: bool
    provider_id: str
    provider_name: str
    provider_ok: bool


class AdminModelUpdate(BaseModel):
    model_id: str = Field(min_length=3, max_length=300)
    hidden: bool
    display_name: str | None = Field(default=None, max_length=100)


class CustomModelWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    emoji: str = Field(default="🤖", min_length=1, max_length=16)
    base_model_id: str = Field(min_length=3, max_length=300)
    system_prompt: str = Field(default="", max_length=20_000)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=20)
    visibility: Literal["private", "public"] = "private"


class CustomModelRead(BaseModel):
    id: str  # use as model_id "persona:{id}"
    model_id: str
    name: str
    description: str
    emoji: str
    base_model_id: str
    system_prompt: str
    knowledge: list[AttachmentRead]
    visibility: Literal["private", "public"]
    is_owner: bool
    created_at: datetime
    updated_at: datetime

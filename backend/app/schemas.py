from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProviderKind = Literal["ollama", "openai_compat", "anthropic"]
Role = Literal["system", "user", "assistant"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Any  # parsed JSON; validated by the tool before it runs


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ChatMessage(BaseModel):
    """A turn sent to a provider. Tool turns only exist inside one request's
    agent loop; saved history is plain user/assistant text."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    # assistant: the tools it asked to run
    tool_calls: list[ToolCall] | None = None
    # tool: which call this answers, and that tool's name
    tool_call_id: str | None = None
    name: str | None = None
    is_error: bool = False
    # assistant: the provider's own representation of the turn, replayed
    # verbatim (e.g. Claude content blocks with thinking signatures)
    provider_state: Any = None


class ChatParams(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None


# Kinds in the model menu: real providers, plus "custom" for saved assistants.
CatalogKind = Literal["ollama", "openai_compat", "anthropic", "custom", "arena"]


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
    # On the done chunk: tools the model wants run before it continues.
    tool_calls: list[ToolCall] | None = None
    provider_state: Any = None


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
    tools: list["ToolTraceRead"] | None = None
    images: list["ImageRef"] | None = None
    # Side-by-side replies: their column. Arena replies are `blind`, and their
    # model_id is hidden until the user votes.
    slot: int | None = None
    blind: bool = False
    created_at: datetime


class SourceRead(BaseModel):
    n: int
    document_id: str | None
    filename: str
    page: int | None
    text: str
    url: str | None = None


class ImageRef(BaseModel):
    """A generated image, served at /api/images/{id}."""

    id: str
    prompt: str


class ToolTraceRead(BaseModel):
    id: str
    name: str
    arguments: Any
    output: str
    error: bool


class ToolInfo(BaseModel):
    id: str
    label: str
    emoji: str
    summary: str


class AttachmentRead(BaseModel):
    kind: Literal["collection", "document"]
    id: str
    name: str


class ConversationDetail(ConversationRead):
    system_prompt: str | None
    share_id: str | None = None
    attachments: list[AttachmentRead] = Field(default_factory=list)
    messages: list[MessageRead]


class RatingsUpdate(BaseModel):
    """Several replies rated at once, e.g. an arena vote: {message_id: 1 | -1}."""

    ratings: dict[int, Literal[1, -1]] = Field(min_length=1, max_length=4)


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
    images: list[ImageRef] | None = None


class SharedChatRead(BaseModel):
    title: str
    messages: list[SharedMessage]
    updated_at: datetime


# --- chat -------------------------------------------------------------------


class ChatStreamRequest(BaseModel):
    """send: add `message` and reply. regenerate: replace the replies to the last
    message, or just reply `message_id`. edit: change user message `message_id`
    to `message`, drop everything after it, reply.

    `model_ids` adds models that answer side by side; model_id "arena:blind"
    lets two hidden models answer."""

    conversation_id: str
    model_id: str = Field(min_length=3, description='Namespaced, e.g. "ollama:llama3.2:1b"')
    model_ids: list[str] = Field(default_factory=list, max_length=3)
    action: Literal["send", "regenerate", "edit"] = "send"
    message: str | None = Field(default=None, min_length=1, max_length=100_000)
    message_id: int | None = None
    # Tool IDs the model may call this turn (custom models add their own).
    tools: list[str] = Field(default_factory=list, max_length=20)
    # Search the web before answering and cite the pages.
    web_search: bool = False
    # Make an image from the message, then reply about it.
    image_generation: bool = False
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
    # A search engine is set up, so chats can search the web.
    web_search: bool = False
    # An image engine is set up, so chats can make images.
    image_generation: bool = False
    # Server speech engines; without them the browser's own speech is used.
    speech_to_text: bool = False
    text_to_speech: bool = False


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


class MemoryRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: datetime


class MemoryWrite(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class MemoryList(BaseModel):
    enabled: bool
    memories: list[MemoryRead]


class MemorySettings(BaseModel):
    enabled: bool


class AdminUserUpdate(BaseModel):
    role: UserRole


class AdminSettings(BaseModel):
    enable_signup: bool
    default_user_role: Literal["user", "pending"]
    # Omitted on update: keep the current tools.
    enabled_tools: list[str] | None = None
    # Provider models the Arena picks from (two per message). Omitted: keep.
    arena_models: list[str] | None = None


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


class WebSearchSettingsRead(BaseModel):
    engine: Literal["", "duckduckgo", "searxng", "brave", "tavily"]
    base_url: str
    result_count: int
    has_key: bool


class WebSearchSettingsUpdate(BaseModel):
    engine: Literal["", "duckduckgo", "searxng", "brave", "tavily"]
    base_url: str = Field(default="", max_length=500)
    result_count: int = Field(default=3, ge=1, le=10)
    # Omit/null to keep the stored key, "" to remove it.
    api_key: str | None = Field(default=None, max_length=1000)


class ImageSettingsRead(BaseModel):
    engine: Literal["", "pollinations", "openai", "automatic1111"]
    base_url: str
    model: str
    size: str
    has_key: bool


class ImageSettingsUpdate(BaseModel):
    engine: Literal["", "pollinations", "openai", "automatic1111"]
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    size: Literal["512x512", "768x768", "1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    # Omit/null to keep the stored key, "" to remove it.
    api_key: str | None = Field(default=None, max_length=1000)


class SpeechPart(BaseModel):
    engine: Literal["", "openai"]
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    voice: str = Field(default="", max_length=100)  # text-to-speech only


class SpeechPartRead(SpeechPart):
    has_key: bool


class AudioSettingsRead(BaseModel):
    stt: SpeechPartRead
    tts: SpeechPartRead


class SpeechPartUpdate(SpeechPart):
    # Omit/null to keep the stored key, "" to remove it.
    api_key: str | None = Field(default=None, max_length=1000)


class AudioSettingsUpdate(BaseModel):
    stt: SpeechPartUpdate
    tts: SpeechPartUpdate


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class Transcription(BaseModel):
    text: str


class ImageTest(BaseModel):
    prompt: str = Field(default="A lighthouse on a cliff at sunset", min_length=1, max_length=500)


class WebSearchTest(BaseModel):
    query: str = Field(default="Open WebUI", min_length=1, max_length=200)


# --- model management ----------------------------------------------------------------


class LeaderboardEntry(BaseModel):
    model_id: str
    elo: int
    matches: int
    wins: int
    losses: int
    ties: int
    likes: int
    dislikes: int


class UsageTotals(BaseModel):
    users: int
    guests: int
    conversations: int
    messages: int
    active_users: int  # in the period
    period_messages: int
    period_tokens: int


class UsageDay(BaseModel):
    date: str
    messages: int
    replies: int
    tokens: int
    active_users: int


class UsageByModel(BaseModel):
    model_id: str
    replies: int
    prompt_tokens: int
    completion_tokens: int
    likes: int
    dislikes: int


class UsageReport(BaseModel):
    days: int
    totals: UsageTotals
    daily: list[UsageDay]
    models: list[UsageByModel]


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
    tool_ids: list[str] = Field(default_factory=list, max_length=20)
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
    tool_ids: list[str]
    visibility: Literal["private", "public"]
    is_owner: bool
    created_at: datetime
    updated_at: datetime

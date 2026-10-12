import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field, SQLModel

from app.rag.vector import Embedding

DEFAULT_TITLE = "New chat"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Provider(SQLModel, table=True):
    __tablename__ = "providers"

    # Short slug (e.g. "ollama", "groq"). It prefixes model IDs as "{id}:{model}",
    # so it must never contain a colon.
    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(max_length=100)
    kind: str = Field(max_length=20)  # "ollama" | "openai_compat"
    base_url: str = Field(max_length=500)
    api_key_encrypted: str | None = Field(default=None)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


def new_id() -> str:
    return uuid.uuid4().hex


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: str = Field(default_factory=new_id, primary_key=True, max_length=32)
    title: str = Field(default=DEFAULT_TITLE, max_length=200)
    # ID of the user who owns the conversation.
    owner_id: str | None = Field(default=None, max_length=64, index=True)
    # Sent to the model as a "system" message ahead of the history.
    system_prompt: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    pinned: bool = Field(default=False)
    archived: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    # Autoincrement keeps messages in insertion order even when timestamps tie.
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    role: str = Field(max_length=20)  # "system" | "user" | "assistant"
    content: str = Field(sa_column=Column(Text, nullable=False))
    # Namespaced model that produced an assistant message; None for user/system.
    model_id: str | None = Field(default=None, max_length=300)
    # User feedback on an assistant reply: 1 (good), -1 (bad), or None.
    rating: int | None = Field(default=None)
    rating_comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Document excerpts the reply was grounded in (JSON list), for citations.
    sources_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Tools the model ran while writing this reply (JSON list), shown with it.
    tools_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=utcnow)


class RateLimitBucket(SQLModel, table=True):
    """Fixed-window hit counter per client. Lives in the database so the limit
    holds across serverless instances."""

    __tablename__ = "rate_limits"

    key: str = Field(primary_key=True, max_length=100)
    window_start: int = Field(primary_key=True)  # epoch seconds
    count: int = Field(default=0)


ROLES = ("admin", "user", "pending")


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=new_id, primary_key=True, max_length=32)
    # Lower-cased. None for guest accounts.
    email: str | None = Field(default=None, max_length=320, unique=True)
    name: str = Field(max_length=100)
    # None for accounts that only sign in with GitHub/Google, and for guests.
    password_hash: str | None = Field(default=None, max_length=255)
    role: str = Field(default="pending", max_length=20)
    is_guest: bool = Field(default=False)
    # Part of every session token; bumping it signs the user out everywhere.
    session_version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    last_active_at: datetime = Field(default_factory=utcnow)


class OAuthAccount(SQLModel, table=True):
    __tablename__ = "oauth_accounts"

    provider: str = Field(primary_key=True, max_length=20)  # "github" | "google"
    subject: str = Field(primary_key=True, max_length=255)  # the provider's user ID
    user_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    created_at: datetime = Field(default_factory=utcnow)


class AppSetting(SQLModel, table=True):
    """Settings admins change at runtime (JSON values), overriding env defaults."""

    __tablename__ = "app_settings"

    key: str = Field(primary_key=True, max_length=100)
    value: str = Field(sa_column=Column(Text, nullable=False))


class SharedChat(SQLModel, table=True):
    """A read-only snapshot of a conversation, viewable by anyone with the link.

    A snapshot (not a live view) so messages added after sharing stay private
    until the owner shares again.
    """

    __tablename__ = "shared_chats"

    id: str = Field(primary_key=True, max_length=43)  # the unguessable link token
    conversation_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    title: str = Field(max_length=200)
    messages_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class KnowledgeCollection(SQLModel, table=True):
    """A named set of documents ("knowledge base") that chats can draw on."""

    __tablename__ = "knowledge_collections"

    id: str = Field(default_factory=new_id, primary_key=True, max_length=32)
    owner_id: str = Field(max_length=32, index=True)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Document(SQLModel, table=True):
    """An uploaded file, stored as its extracted text chunks (not the file itself)."""

    __tablename__ = "documents"

    id: str = Field(default_factory=new_id, primary_key=True, max_length=32)
    owner_id: str = Field(max_length=32, index=True)
    # None: attached to a single chat rather than a knowledge base.
    collection_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    filename: str = Field(max_length=255)
    size_bytes: int = Field(default=0)
    page_count: int | None = Field(default=None)
    chunk_count: int = Field(default=0)
    # Set when the document is searchable by keyword only (embedding failed).
    warning: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow)


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunks"

    id: int | None = Field(default=None, primary_key=True)
    document_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    position: int
    page: int | None = Field(default=None)
    text: str = Field(sa_column=Column(Text, nullable=False))
    embedding: list[float] | None = Field(default=None, sa_column=Column(Embedding, nullable=True))
    # Which engine:model produced the embedding; vectors from different models
    # aren't comparable, so search only uses chunks matching the current one.
    embedding_model: str | None = Field(default=None, max_length=200, index=True)


class ConversationAttachment(SQLModel, table=True):
    """Knowledge bases or single documents a chat retrieves from."""

    __tablename__ = "conversation_attachments"

    conversation_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    kind: str = Field(primary_key=True, max_length=20)  # "collection" | "document"
    ref_id: str = Field(primary_key=True, max_length=32)


class ModelSetting(SQLModel, table=True):
    """Admin overrides for a provider model: hide it, or give it a friendlier name."""

    __tablename__ = "model_settings"

    model_id: str = Field(primary_key=True, max_length=300)  # namespaced "provider:model"
    hidden: bool = Field(default=False)
    display_name: str | None = Field(default=None, max_length=100)


class CustomModel(SQLModel, table=True):
    """A saved assistant: a base model plus instructions and knowledge."""

    __tablename__ = "custom_models"

    # Used in model IDs as "persona:{id}", so it's a slug without colons.
    id: str = Field(primary_key=True, max_length=64)
    owner_id: str = Field(max_length=32, index=True)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    emoji: str = Field(default="🤖", max_length=16)
    base_model_id: str = Field(max_length=300)
    system_prompt: str = Field(
        default="", sa_column=Column(Text, nullable=False, server_default="")
    )
    # JSON list of knowledge collection IDs owned by the creator.
    knowledge_json: str = Field(
        default="[]", sa_column=Column(Text, nullable=False, server_default="[]")
    )
    # JSON list of tool IDs always offered when chatting with this model.
    tools_json: str = Field(
        default="[]", sa_column=Column(Text, nullable=False, server_default="[]")
    )
    # "private": only the creator; "public": every approved user (admins only).
    visibility: str = Field(default="private", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

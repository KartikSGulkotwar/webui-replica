import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field, SQLModel

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
    created_at: datetime = Field(default_factory=utcnow)

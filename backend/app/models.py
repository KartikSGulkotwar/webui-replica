from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


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

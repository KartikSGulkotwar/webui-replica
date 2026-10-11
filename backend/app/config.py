from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WebUI Replica"
    database_url: str = "sqlite:///./webui.db"
    encryption_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    # Run Alembic migrations on startup. Tests turn this off and create tables directly.
    auto_migrate: bool = True
    # Public demos have no login, so lock provider management there.
    providers_read_only: bool = False
    # Messages per minute per client IP on /api/chat/stream; 0 disables.
    chat_rate_limit_per_minute: int = 20
    # How many reverse proxies in front of the backend append to X-Forwarded-For
    # (1 behind nginx or Render). 0 trusts no header and uses the socket address.
    trusted_proxy_hops: int = 0

    ollama_base_url: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, v: str) -> str:
        # Neon/Render/Heroku hand out postgres:// or postgresql:// URLs, which
        # SQLAlchemy maps to psycopg2; we ship psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

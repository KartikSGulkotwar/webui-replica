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
    # --- accounts -------------------------------------------------------------
    # Signs session tokens. If empty, derived from ENCRYPTION_KEY; if that is also
    # empty, a random per-process key is used (sessions end on restart).
    secret_key: str = ""
    session_days: int = 7
    # Initial values; admins can change both at runtime in the admin panel.
    enable_signup: bool = True
    default_user_role: str = "pending"  # "pending" (admin approves) or "user"
    # "Continue as guest" for public demos: a throwaway account per visitor.
    guest_access: bool = False
    # Create this admin on startup/deploy if it doesn't exist (so a public deploy
    # isn't claimed by whoever signs up first).
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Admin"
    # Base URL for OAuth redirects, e.g. https://webui-replica.vercel.app.
    # Empty: derived from the request (works behind Vercel and nginx).
    public_url: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    # Sign-up/login/guest attempts per minute per client IP.
    auth_rate_limit_per_minute: int = 10

    # --- documents (RAG) ------------------------------------------------------
    # Upload size limit. Vercel caps request bodies at 4.5 MB, so use 4 there.
    max_upload_mb: int = 10
    # Initial embedding settings; admins change them in the admin panel.
    # Engine "" means keyword (BM25) search only.
    rag_embedding_engine: str = ""
    rag_embedding_base_url: str = ""
    rag_embedding_model: str = ""
    rag_embedding_api_key: str = ""

    # Tools the model may call (comma-separated); admins change this at runtime.
    enabled_tools: str = "calculator,current_time,fetch_url,web_search,add_memory"
    # Arena: provider models (comma-separated IDs) that answer blind side by side.
    arena_models: str = ""
    # Web search: duckduckgo (no key), searxng (base URL), brave or tavily (API key); blank = off.
    web_search_engine: str = ""
    web_search_base_url: str = ""
    web_search_api_key: str = ""
    web_search_result_count: int = 3

    # Model preselected for visitors who haven't picked one, e.g. "groq:openai/gpt-oss-120b".
    default_model: str = ""
    # Messages per minute per client IP on /api/chat/stream; 0 disables.
    chat_rate_limit_per_minute: int = 20
    # How many reverse proxies in front of the backend append to X-Forwarded-For
    # (1 behind nginx or Render). 0 trusts no header and uses the socket address.
    trusted_proxy_hops: int = 0

    ollama_base_url: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    anthropic_api_key: str = ""

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

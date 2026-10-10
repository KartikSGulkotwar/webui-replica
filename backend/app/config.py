from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WebUI Replica"
    database_url: str = "sqlite:///./webui.db"
    encryption_key: str = ""
    frontend_origin: str = "http://localhost:5173"

    ollama_base_url: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

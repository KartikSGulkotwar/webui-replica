from collections.abc import Iterator

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.config import Settings
from app.crypto import KeyCipher
from app.main import create_app

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        encryption_key=TEST_KEY,
        auto_migrate=False,
        chat_rate_limit_per_minute=0,
        trusted_proxy_hops=0,
        providers_read_only=False,
        isolate_chats_by_browser=False,
        default_model="",
        ollama_base_url="",
        openai_compat_base_url="",
        openai_compat_api_key="",
    )


@pytest.fixture
def cipher() -> KeyCipher:
    return KeyCipher(TEST_KEY)


@pytest.fixture
def app(settings: Settings):
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    return app


@pytest.fixture
def session(app) -> Iterator[Session]:
    with Session(app.state.engine) as session:
        yield session


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as client:
        yield client

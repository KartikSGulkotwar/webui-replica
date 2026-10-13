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
        default_model="",
        auth_rate_limit_per_minute=0,
        enable_signup=True,
        default_user_role="pending",
        guest_access=False,
        admin_email="",
        admin_password="",
        secret_key="",
        public_url="",
        github_client_id="",
        github_client_secret="",
        google_client_id="",
        google_client_secret="",
        ollama_base_url="",
        openai_compat_base_url="",
        openai_compat_api_key="",
        anthropic_api_key="",
        max_upload_mb=10,
        enabled_tools="calculator,current_time,fetch_url,web_search,add_memory,generate_image",
        rag_embedding_engine="",
        rag_embedding_base_url="",
        rag_embedding_model="",
        rag_embedding_api_key="",
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


PASSWORD = "correct horse battery"


def signup(client: TestClient, email: str, name: str = "Test User") -> dict:
    resp = client.post(
        "/api/auth/signup", json={"name": name, "email": email, "password": PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def anon_client(app) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """Signed in as the first account, which is the admin."""
    with TestClient(app) as client:
        signup(client, "admin@example.com", "Admin")
        yield client


@pytest.fixture
def user_client(app, client) -> Iterator[TestClient]:
    """A second, approved (role "user") account."""
    with TestClient(app) as other:
        user = signup(other, "user@example.com", "Regular User")
        assert client.patch(f"/api/admin/users/{user['id']}", json={"role": "user"}).is_success
        yield other


@pytest.fixture
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as client:
        yield client

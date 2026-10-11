import pytest
from sqlmodel import select

from app.crypto import EncryptionError, KeyCipher
from app.models import Provider, User
from app.seed import guess_provider_name, seed_providers


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("https://api.groq.com/openai/v1", "Groq"),
        ("https://openrouter.ai/api/v1", "OpenRouter"),
        ("https://api.openai.com/v1", "OpenAI"),
        ("http://localhost:1234/v1", "OpenAI-compatible"),
        ("https://notgroq.com/v1", "OpenAI-compatible"),
    ],
)
def test_guess_provider_name(url: str, name: str) -> None:
    assert guess_provider_name(url) == name


def test_seed_creates_providers_with_encrypted_key(session, settings, cipher) -> None:
    settings.ollama_base_url = "http://ollama:11434"
    settings.openai_compat_base_url = "https://api.groq.com/openai/v1"
    settings.openai_compat_api_key = "gsk-secret"

    assert seed_providers(session, settings, cipher) == ["ollama", "groq"]

    groq = session.get(Provider, "groq")
    assert groq.kind == "openai_compat" and groq.name == "Groq"
    assert groq.api_key_encrypted and "gsk-secret" not in groq.api_key_encrypted
    assert cipher.decrypt(groq.api_key_encrypted) == "gsk-secret"
    assert session.get(Provider, "ollama").api_key_encrypted is None


def test_seed_skips_when_table_not_empty(session, settings, cipher) -> None:
    session.add(Provider(id="mine", name="Mine", kind="ollama", base_url="http://x"))
    session.commit()
    settings.ollama_base_url = "http://ollama:11434"

    assert seed_providers(session, settings, cipher) == []
    assert [p.id for p in session.exec(select(Provider)).all()] == ["mine"]


def test_seed_with_key_but_no_encryption_key_fails(session, settings) -> None:
    settings.openai_compat_base_url = "https://api.openai.com/v1"
    settings.openai_compat_api_key = "sk-x"
    with pytest.raises(EncryptionError):
        seed_providers(session, settings, KeyCipher(""))


def test_seed_nothing_configured(session, settings, cipher) -> None:
    assert seed_providers(session, settings, cipher) == []


def test_seed_admin_creates_admin_once(session, settings) -> None:
    from app.security import verify_password
    from app.seed import seed_admin

    settings.admin_email = "Owner@Example.com"
    settings.admin_password = "a-strong-password"
    assert seed_admin(session, settings) is True
    assert seed_admin(session, settings) is False  # already exists
    owner = session.exec(select(User).where(User.email == "owner@example.com")).one()
    assert owner.role == "admin" and verify_password(owner.password_hash, "a-strong-password")


def test_seed_admin_promotes_existing_account(session, settings) -> None:
    from app.seed import seed_admin

    session.add(User(email="owner@example.com", name="O", role="pending"))
    session.commit()
    settings.admin_email = "owner@example.com"
    settings.admin_password = "ignored-for-existing"
    assert seed_admin(session, settings) is False
    assert session.exec(select(User)).one().role == "admin"


def test_seed_admin_needs_email_and_password(session, settings) -> None:
    from app.seed import seed_admin

    settings.admin_email = "owner@example.com"
    assert seed_admin(session, settings) is False

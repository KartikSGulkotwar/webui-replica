import pytest

from app.crypto import KeyCipher
from app.models import Provider
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.registry import ProviderRegistry


@pytest.fixture
def registry(http, cipher) -> ProviderRegistry:
    return ProviderRegistry(http, cipher)


def add(session, **kw) -> Provider:
    row = Provider(**kw)
    session.add(row)
    session.commit()
    return row


def test_sync_builds_enabled_providers(session, registry, cipher) -> None:
    add(session, id="ollama", name="Ollama", kind="ollama", base_url="http://o")
    add(
        session,
        id="groq",
        name="Groq",
        kind="openai_compat",
        base_url="http://g",
        api_key_encrypted=cipher.encrypt("gsk"),
    )
    add(session, id="off", name="Off", kind="ollama", base_url="http://x", enabled=False)

    registry.sync(session)

    assert {e.id for e in registry.entries()} == {"ollama", "groq"}
    assert isinstance(registry.get("ollama"), OllamaProvider)
    groq = registry.get("groq")
    assert isinstance(groq, OpenAICompatProvider) and groq.api_key == "gsk"
    with pytest.raises(ProviderError, match="not found or disabled"):
        registry.get("off")


def test_sync_caches_unchanged_and_rebuilds_changed(session, registry) -> None:
    row = add(session, id="ollama", name="Ollama", kind="ollama", base_url="http://a")
    registry.sync(session)
    first = registry.get("ollama")

    registry.sync(session)
    assert registry.get("ollama") is first

    row.base_url = "http://b"
    session.add(row)
    session.commit()
    registry.sync(session)
    assert registry.get("ollama") is not first
    assert registry.get("ollama").base_url == "http://b"


def test_sync_drops_disabled_and_deleted(session, registry) -> None:
    row = add(session, id="ollama", name="Ollama", kind="ollama", base_url="http://a")
    registry.sync(session)
    row.enabled = False
    session.add(row)
    session.commit()
    registry.sync(session)
    assert registry.entries() == []


def test_undecryptable_key_is_reported_not_fatal(session, http) -> None:
    from cryptography.fernet import Fernet

    other = KeyCipher(Fernet.generate_key().decode())
    add(
        session,
        id="bad",
        name="Bad",
        kind="openai_compat",
        base_url="http://b",
        api_key_encrypted=other.encrypt("k"),
    )
    add(session, id="ok", name="OK", kind="ollama", base_url="http://o")
    registry = ProviderRegistry(http, KeyCipher(Fernet.generate_key().decode()))

    registry.sync(session)

    bad = next(e for e in registry.entries() if e.id == "bad")
    assert bad.provider is None and "cannot be decrypted" in bad.error
    assert registry.get("ok") is not None
    with pytest.raises(ProviderError, match="cannot be decrypted"):
        registry.get("bad")

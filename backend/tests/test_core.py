import pytest
from cryptography.fernet import Fernet

from app.crypto import EncryptionError, KeyCipher
from app.providers.base import split_model_id


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("groq:llama-3.1-8b", ("groq", "llama-3.1-8b")),
        ("ollama:llama3.2:1b", ("ollama", "llama3.2:1b")),
        ("openrouter:meta-llama/llama-3-8b:free", ("openrouter", "meta-llama/llama-3-8b:free")),
    ],
)
def test_split_model_id(model_id: str, expected: tuple[str, str]) -> None:
    assert split_model_id(model_id) == expected


@pytest.mark.parametrize("bad", ["", "nocolon", ":model", "provider:"])
def test_split_model_id_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        split_model_id(bad)


def test_cipher_roundtrip() -> None:
    cipher = KeyCipher(Fernet.generate_key().decode())
    token = cipher.encrypt("sk-secret")
    assert token != "sk-secret"
    assert cipher.decrypt(token) == "sk-secret"


def test_cipher_without_key_fails_on_use() -> None:
    cipher = KeyCipher("")
    assert not cipher.configured
    with pytest.raises(EncryptionError, match="ENCRYPTION_KEY is not set"):
        cipher.encrypt("x")


def test_cipher_rejects_invalid_key() -> None:
    with pytest.raises(EncryptionError, match="not a valid Fernet key"):
        KeyCipher("too-short")


def test_cipher_wrong_key() -> None:
    token = KeyCipher(Fernet.generate_key().decode()).encrypt("x")
    with pytest.raises(EncryptionError, match="cannot be decrypted"):
        KeyCipher(Fernet.generate_key().decode()).decrypt(token)

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(RuntimeError):
    pass


class KeyCipher:
    """Encrypts provider API keys at rest with Fernet.

    The cipher can be constructed without a key so the app still boots when no
    provider needs one; it only fails when asked to encrypt or decrypt.
    """

    def __init__(self, key: str | None) -> None:
        self._fernet: Fernet | None = None
        if key:
            try:
                self._fernet = Fernet(key.encode())
            except (ValueError, TypeError) as exc:
                raise EncryptionError(
                    "ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64 bytes)"
                ) from exc

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise EncryptionError(
                "ENCRYPTION_KEY is not set; it is required to store or use provider API keys"
            )
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        return self._require().encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._require().decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise EncryptionError(
                "Stored API key cannot be decrypted; was ENCRYPTION_KEY changed?"
            ) from exc

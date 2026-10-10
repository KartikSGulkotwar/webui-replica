import logging
import re
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.config import Settings
from app.crypto import KeyCipher
from app.models import Provider

logger = logging.getLogger(__name__)

KNOWN_HOSTS = {
    "groq.com": "Groq",
    "openrouter.ai": "OpenRouter",
    "openai.com": "OpenAI",
    "together.xyz": "Together",
    "together.ai": "Together",
}


def guess_provider_name(base_url: str) -> str:
    host = urlparse(base_url).hostname or ""
    for domain, name in KNOWN_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return "OpenAI-compatible"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "provider"


def seed_providers(session: Session, settings: Settings, cipher: KeyCipher) -> list[str]:
    """Create providers from env vars, but only into an empty table, so edits made
    in the UI are never overwritten on restart. Returns the IDs created."""
    if session.exec(select(Provider).limit(1)).first() is not None:
        return []

    rows: list[Provider] = []
    if settings.ollama_base_url:
        rows.append(
            Provider(id="ollama", name="Ollama", kind="ollama", base_url=settings.ollama_base_url)
        )
    if settings.openai_compat_base_url:
        name = guess_provider_name(settings.openai_compat_base_url)
        key = settings.openai_compat_api_key
        rows.append(
            Provider(
                id=slugify(name),
                name=name,
                kind="openai_compat",
                base_url=settings.openai_compat_base_url,
                # Fails loudly if a key is given without ENCRYPTION_KEY.
                api_key_encrypted=cipher.encrypt(key) if key else None,
            )
        )
    for row in rows:
        session.add(row)
    session.commit()
    if rows:
        logger.info("Seeded providers: %s", ", ".join(r.id for r in rows))
    return [r.id for r in rows]

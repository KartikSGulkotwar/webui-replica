"""Image generation for chat: settings, prompts, and stored images."""

import asyncio
import json
import logging

from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from app.config import Settings
from app.crypto import EncryptionError, KeyCipher
from app.images.engines import ImageConfig
from app.models import AppSetting, GeneratedImage, Message
from app.providers.base import BaseProvider, ProviderError
from app.schemas import ChatMessage, ChatParams

logger = logging.getLogger(__name__)

SETTINGS_KEY = "image_generation"
PROMPT_TIMEOUT = 20.0


# --- settings ----------------------------------------------------------------------


def load_image_settings(session: Session, settings: Settings) -> dict:
    """Stored admin settings (api key encrypted), falling back to env defaults."""
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is not None:
        return json.loads(row.value)
    return {
        "engine": settings.image_engine,
        "base_url": settings.image_base_url,
        "model": settings.image_model,
        "size": settings.image_size,
        "api_key_encrypted": None,
        "env_api_key": bool(settings.image_api_key),
    }


def save_image_settings(session: Session, values: dict) -> None:
    row = session.get(AppSetting, SETTINGS_KEY) or AppSetting(key=SETTINGS_KEY, value="{}")
    row.value = json.dumps(values)
    session.add(row)
    session.commit()


def image_config(session: Session, settings: Settings, cipher: KeyCipher) -> ImageConfig:
    stored = load_image_settings(session, settings)
    api_key = None
    if stored.get("api_key_encrypted"):
        try:
            api_key = cipher.decrypt(stored["api_key_encrypted"])
        except EncryptionError:
            logger.warning("Image API key can't be decrypted; using no key")
    elif stored.get("env_api_key"):
        api_key = settings.image_api_key
    return ImageConfig(
        engine=stored.get("engine") or "",
        base_url=stored.get("base_url") or "",
        api_key=api_key,
        model=stored.get("model") or "",
        size=stored.get("size") or "1024x1024",
    )


# --- prompts -----------------------------------------------------------------------


async def make_image_prompt(provider: BaseProvider, model: str, history: list[ChatMessage]) -> str:
    """What to draw. A first request is drawn as written; a follow-up ("now make
    it blue") is rewritten by the model into a complete, standalone prompt."""
    turns = [m for m in history if m.role in ("user", "assistant") and m.content.strip()]
    request = next((m.content for m in reversed(turns) if m.role == "user"), "")
    if len([m for m in turns if m.role == "user"]) <= 1:
        return request.strip()
    transcript = "\n".join(f"{m.role}: {m.content[:1000]}" for m in turns[-6:])
    prompt = [
        ChatMessage(
            role="system",
            content=(
                "You write prompts for an image generator. Turn the last message of the "
                "conversation into one complete image description (under 60 words) that makes "
                "sense on its own, keeping details from earlier requests it refers to. "
                "Reply with the prompt only."
            ),
        ),
        ChatMessage(
            role="user", content=f"<conversation>\n{transcript}\n</conversation>\n\nImage prompt:"
        ),
    ]

    async def ask() -> str:
        parts = []
        async for chunk in provider.stream_chat(model, prompt, ChatParams(temperature=0.3)):
            parts.append(chunk.delta)
            if chunk.done:
                break
        return "".join(parts).strip().strip("\"'` ")

    try:
        rewritten = await asyncio.wait_for(ask(), PROMPT_TIMEOUT)
    except (ProviderError, TimeoutError) as exc:
        logger.info("Image prompt rewrite failed, using the message as written: %s", exc)
        rewritten = ""
    return rewritten[:2000] or request.strip()


# --- storage -----------------------------------------------------------------------


def store_image(
    engine: Engine,
    owner_id: str,
    conversation_id: str | None,
    prompt: str,
    data: bytes,
    mime: str,
) -> str:
    with Session(engine) as session:
        image = GeneratedImage(
            owner_id=owner_id, conversation_id=conversation_id, prompt=prompt, data=data, mime=mime
        )
        session.add(image)
        session.commit()
        return image.id


def delete_message_images(session: Session, messages: list[Message]) -> None:
    """Remove the stored images of replies that are being deleted."""
    ids = [
        image["id"]
        for m in messages
        if m.images_json
        for image in json.loads(m.images_json)
        if isinstance(image, dict) and "id" in image
    ]
    if ids:
        session.exec(delete(GeneratedImage).where(col(GeneratedImage.id).in_(ids)))


def image_ids_in(session: Session, conversation_id: str) -> set[str]:
    return set(
        session.exec(
            select(GeneratedImage.id).where(GeneratedImage.conversation_id == conversation_id)
        )
    )

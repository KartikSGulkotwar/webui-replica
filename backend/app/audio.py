"""Speech: transcription (speech-to-text) and read-aloud (text-to-speech).

Both are optional server engines speaking the OpenAI audio API, which OpenAI,
Groq (Whisper, Orpheus) and many local servers implement. Without them the
browser's own speech features are used.
"""

import json
import logging
from dataclasses import dataclass

import httpx
from sqlmodel import Session

from app.config import Settings
from app.crypto import EncryptionError, KeyCipher
from app.models import AppSetting

logger = logging.getLogger(__name__)

SETTINGS_KEY = "audio"
MAX_AUDIO_BYTES = 4_000_000  # under Vercel's 4.5 MB request limit (~4 min of speech)
MAX_SPEECH_CHARS = 4000
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class AudioError(Exception):
    pass


@dataclass(frozen=True)
class SpeechToText:
    engine: str = ""  # "" = the browser's own; "openai" = OpenAI-compatible
    base_url: str = ""
    api_key: str | None = None
    model: str = ""

    @property
    def enabled(self) -> bool:
        return self.engine == "openai" and bool(self.base_url and self.model)


@dataclass(frozen=True)
class TextToSpeech:
    engine: str = ""
    base_url: str = ""
    api_key: str | None = None
    model: str = ""
    voice: str = ""

    @property
    def enabled(self) -> bool:
        return self.engine == "openai" and bool(self.base_url and self.model)


# --- settings ----------------------------------------------------------------------


def load_audio_settings(session: Session, settings: Settings) -> dict:
    """Stored admin settings (keys encrypted), falling back to env defaults."""
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is not None:
        return json.loads(row.value)
    return {
        "stt": {
            "engine": settings.stt_engine,
            "base_url": settings.stt_base_url,
            "model": settings.stt_model,
            "api_key_encrypted": None,
            "env_api_key": bool(settings.stt_api_key),
        },
        "tts": {
            "engine": settings.tts_engine,
            "base_url": settings.tts_base_url,
            "model": settings.tts_model,
            "voice": settings.tts_voice,
            "api_key_encrypted": None,
            "env_api_key": bool(settings.tts_api_key),
        },
    }


def save_audio_settings(session: Session, values: dict) -> None:
    row = session.get(AppSetting, SETTINGS_KEY) or AppSetting(key=SETTINGS_KEY, value="{}")
    row.value = json.dumps(values)
    session.add(row)
    session.commit()


def _key(part: dict, cipher: KeyCipher, env_key: str) -> str | None:
    if part.get("api_key_encrypted"):
        try:
            return cipher.decrypt(part["api_key_encrypted"])
        except EncryptionError:
            logger.warning("An audio API key can't be decrypted; using no key")
            return None
    return env_key if part.get("env_api_key") else None


def audio_config(
    session: Session, settings: Settings, cipher: KeyCipher
) -> tuple[SpeechToText, TextToSpeech]:
    stored = load_audio_settings(session, settings)
    stt, tts = stored.get("stt") or {}, stored.get("tts") or {}
    return (
        SpeechToText(
            engine=stt.get("engine") or "",
            base_url=stt.get("base_url") or "",
            api_key=_key(stt, cipher, settings.stt_api_key),
            model=stt.get("model") or "",
        ),
        TextToSpeech(
            engine=tts.get("engine") or "",
            base_url=tts.get("base_url") or "",
            api_key=_key(tts, cipher, settings.tts_api_key),
            model=tts.get("model") or "",
            voice=tts.get("voice") or "",
        ),
    )


# --- engines -----------------------------------------------------------------------


def _headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _error(resp: httpx.Response, what: str) -> AudioError:
    if resp.status_code in (401, 403):
        return AudioError(f"The {what} service rejected the API key")
    if resp.status_code == 429:
        return AudioError(f"The {what} service's rate limit was reached; try again shortly")
    detail = ""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        detail = (err.get("message") if isinstance(err, dict) else err) or ""
    except ValueError:
        pass
    return AudioError(f"The {what} service returned HTTP {resp.status_code} {detail[:200]}".strip())


async def transcribe(
    http: httpx.AsyncClient, config: SpeechToText, filename: str, data: bytes, mime: str
) -> str:
    if not config.enabled:
        raise AudioError("Speech-to-text isn't set up on the server")
    try:
        resp = await http.post(
            f"{config.base_url}/audio/transcriptions",
            data={"model": config.model},
            files={"file": (filename, data, mime)},
            headers=_headers(config.api_key),
            timeout=TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        raise AudioError("The speech-to-text service took too long") from exc
    except httpx.HTTPError as exc:
        raise AudioError(
            f"Couldn't reach the speech-to-text service: {exc.__class__.__name__}"
        ) from exc
    if resp.status_code >= 400:
        raise _error(resp, "speech-to-text")
    try:
        return str(resp.json().get("text") or "").strip()
    except ValueError as exc:
        raise AudioError("The speech-to-text service returned something unexpected") from exc


def _audio_mime(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"fLaC"):
        return "audio/flac"
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if data[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return "audio/aac"
    raise AudioError("The text-to-speech service didn't return audio")


async def speak(http: httpx.AsyncClient, config: TextToSpeech, text: str) -> tuple[bytes, str]:
    """Spoken audio for `text`: (bytes, media type)."""
    if not config.enabled:
        raise AudioError("Text-to-speech isn't set up on the server")
    text = text.strip()[:MAX_SPEECH_CHARS]
    if not text:
        raise AudioError("There's nothing to read")
    body: dict = {"model": config.model, "input": text}
    if config.voice:
        body["voice"] = config.voice
    # Some models (Groq's Orpheus) only produce WAV; MP3 is smaller elsewhere.
    body["response_format"] = "wav" if "orpheus" in config.model else "mp3"
    try:
        resp = await http.post(
            f"{config.base_url}/audio/speech",
            json=body,
            headers=_headers(config.api_key),
            timeout=TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        raise AudioError("The text-to-speech service took too long") from exc
    except httpx.HTTPError as exc:
        raise AudioError(
            f"Couldn't reach the text-to-speech service: {exc.__class__.__name__}"
        ) from exc
    if resp.status_code >= 400:
        raise _error(resp, "text-to-speech")
    return resp.content, _audio_mime(resp.content)

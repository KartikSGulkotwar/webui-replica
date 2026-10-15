"""Server speech engines: transcription, read-aloud, and their admin settings."""

import json

import respx

import app.routers.audio as audio_router

GROQ = "https://api.groq.test/openai/v1"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24
MP3 = b"ID3\x04\x00\x00" + b"\x00" * 24


def configure(client, stt: dict | None = None, tts: dict | None = None) -> dict:
    off = {"engine": "", "base_url": "", "model": "", "voice": ""}
    resp = client.put("/api/admin/audio", json={"stt": stt or off, "tts": tts or off})
    assert resp.status_code == 200, resp.text
    return resp.json()


def whisper(client) -> None:
    configure(
        client,
        stt={
            "engine": "openai",
            "base_url": f"{GROQ}/",
            "model": "whisper-large-v3-turbo",
            "api_key": "gsk",
        },
    )


def upload(client, data: bytes = b"\x1aE\xdf\xa3webm-audio", mime: str = "audio/webm"):
    return client.post("/api/audio/transcriptions", files={"file": ("speech.webm", data, mime)})


# --- settings ----------------------------------------------------------------------------


def test_audio_settings(client, user_client) -> None:
    empty = {"engine": "", "base_url": "", "model": "", "voice": "", "has_key": False}
    assert client.get("/api/admin/audio").json() == {"stt": empty, "tts": empty}
    config = client.get("/api/config").json()
    assert config["speech_to_text"] is False and config["text_to_speech"] is False

    bad = client.put(
        "/api/admin/audio",
        json={"stt": {"engine": "openai", "base_url": GROQ}, "tts": {"engine": ""}},
    )
    assert bad.status_code == 422 and "Speech-to-text" in bad.json()["detail"]

    whisper(client)
    saved = client.get("/api/admin/audio").json()["stt"]
    assert saved["base_url"] == GROQ and saved["has_key"]
    # Saving again without a key keeps it.
    configure(client, stt={"engine": "openai", "base_url": GROQ, "model": "whisper-large-v3-turbo"})
    assert client.get("/api/admin/audio").json()["stt"]["has_key"]
    assert client.get("/api/config").json()["speech_to_text"] is True
    assert user_client.get("/api/admin/audio").status_code == 403


# --- transcription -----------------------------------------------------------------------


def test_transcription_needs_an_engine(client) -> None:
    assert upload(client).status_code == 400


@respx.mock
def test_transcription(client) -> None:
    whisper(client)
    route = respx.post(f"{GROQ}/audio/transcriptions").respond(json={"text": "  Hello there. "})
    resp = upload(client)
    assert resp.status_code == 200 and resp.json() == {"text": "Hello there."}
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer gsk"
    body = request.content
    assert b'name="model"' in body and b"whisper-large-v3-turbo" in body
    assert b'filename="speech.webm"' in body and b"webm-audio" in body


@respx.mock
def test_transcription_errors(client, monkeypatch) -> None:
    whisper(client)
    assert upload(client, b"").status_code == 422
    assert upload(client, b"%PDF", "application/pdf").status_code == 415
    monkeypatch.setattr(audio_router, "MAX_AUDIO_BYTES", 5)
    assert upload(client, b"123456").status_code == 413
    monkeypatch.undo()
    respx.post(f"{GROQ}/audio/transcriptions").respond(401, json={"error": {"message": "x"}})
    resp = upload(client)
    assert resp.status_code == 502 and "rejected the API key" in resp.json()["detail"]


# --- speech ---------------------------------------------------------------------------------


@respx.mock
def test_speech(client, user_client) -> None:
    assert client.post("/api/audio/speech", json={"text": "hi"}).status_code == 400
    configure(
        client,
        tts={
            "engine": "openai",
            "base_url": "https://api.openai.test/v1",
            "model": "tts-1",
            "voice": "alloy",
            "api_key": "sk",
        },
    )
    route = respx.post("https://api.openai.test/v1/audio/speech").respond(content=MP3)
    resp = user_client.post("/api/audio/speech", json={"text": "Hello"})
    assert resp.status_code == 200 and resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == MP3
    assert json.loads(route.calls.last.request.content) == {
        "model": "tts-1",
        "input": "Hello",
        "voice": "alloy",
        "response_format": "mp3",
    }
    route.respond(content=b"<html>oops</html>")
    assert user_client.post("/api/audio/speech", json={"text": "Hi"}).status_code == 502


@respx.mock
def test_orpheus_asks_for_wav(client) -> None:
    configure(
        client,
        tts={
            "engine": "openai",
            "base_url": GROQ,
            "model": "canopylabs/orpheus-v1-english",
            "voice": "tara",
        },
    )
    route = respx.post(f"{GROQ}/audio/speech").respond(content=WAV)
    resp = client.post("/api/audio/speech", json={"text": "Hi"})
    assert resp.headers["content-type"] == "audio/wav"
    assert json.loads(route.calls.last.request.content)["response_format"] == "wav"

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from app.audio import MAX_AUDIO_BYTES, AudioError, audio_config, speak, transcribe
from app.auth import ActiveUserDep
from app.db import SessionDep
from app.ratelimit import limit_chat
from app.schemas import SpeechRequest, Transcription

router = APIRouter(prefix="/api/audio", tags=["audio"], dependencies=[Depends(limit_chat)])


@router.post("/transcriptions", response_model=Transcription)
async def create_transcription(
    request: Request,
    session: SessionDep,
    user: ActiveUserDep,
    file: Annotated[UploadFile, File()],
) -> Transcription:
    """Speech to text with the server's engine (the microphone button, voice mode)."""
    stt, _ = audio_config(session, request.app.state.settings, request.app.state.cipher)
    if not stt.enabled:
        raise HTTPException(status_code=400, detail="Speech-to-text isn't set up on the server")
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="The recording is too long (4 MB at most)")
    if not data:
        raise HTTPException(status_code=422, detail="The recording is empty")
    mime = (file.content_type or "application/octet-stream").split(";")[0]
    if not (mime.startswith("audio/") or mime in ("video/webm", "application/octet-stream")):
        raise HTTPException(status_code=415, detail="That isn't an audio file")
    try:
        text = await transcribe(
            request.app.state.http, stt, file.filename or "speech.webm", data, mime
        )
    except AudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Transcription(text=text)


@router.post("/speech")
async def create_speech(
    body: SpeechRequest, request: Request, session: SessionDep, user: ActiveUserDep
) -> Response:
    """Text to speech with the server's engine (the read-aloud button)."""
    _, tts = audio_config(session, request.app.state.settings, request.app.state.cipher)
    if not tts.enabled:
        raise HTTPException(status_code=400, detail="Text-to-speech isn't set up on the server")
    try:
        audio, mime = await speak(request.app.state.http, tts, body.text)
    except AudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=audio, media_type=mime, headers={"Cache-Control": "no-store"})

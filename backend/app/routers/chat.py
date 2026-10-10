import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlmodel import Session

from app.db import SessionDep
from app.models import DEFAULT_TITLE, Conversation, Message, utcnow
from app.providers.base import BaseProvider, ProviderError, split_model_id
from app.providers.registry import RegistryDep
from app.ratelimit import limit_chat
from app.routers.conversations import get_conversation_or_404, list_messages
from app.schemas import ChatMessage, ChatParams, ChatStreamRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

TITLE_WORDS = 6
TITLE_MAX_CHARS = 60


def make_title(text: str) -> str:
    """Title from the first few words of the first user message (no LLM call)."""
    words = text.split()
    title = " ".join(words[:TITLE_WORDS])
    truncated = len(words) > TITLE_WORDS
    if len(title) > TITLE_MAX_CHARS:
        title = title[:TITLE_MAX_CHARS].rstrip()
        truncated = True
    return (title + "…") if truncated else title or DEFAULT_TITLE


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def save_assistant_message(
    engine: Engine, conversation_id: str, model_id: str, content: str
) -> int | None:
    with Session(engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:  # deleted while streaming
            return None
        message = Message(
            conversation_id=conversation_id, role="assistant", content=content, model_id=model_id
        )
        conversation.updated_at = utcnow()
        session.add(message)
        session.add(conversation)
        session.commit()
        return message.id


async def stream_and_persist(
    engine: Engine,
    provider: BaseProvider,
    conversation_id: str,
    model_id: str,
    model: str,
    history: list[ChatMessage],
    params: ChatParams,
) -> AsyncIterator[str]:
    """Relay provider chunks as normalized SSE and save the assistant reply.

    The reply is saved however the stream ends: on completion, on a provider
    error, or when the client disconnects (Stop button), so partial answers
    survive a refresh. Nothing is saved if no text was produced.
    """
    parts: list[str] = []
    saved = False

    def save() -> int | None:
        nonlocal saved
        saved = True
        content = "".join(parts)
        if not content:
            return None
        return save_assistant_message(engine, conversation_id, model_id, content)

    try:
        async for chunk in provider.stream_chat(model, history, params):
            if chunk.delta:
                parts.append(chunk.delta)
                yield sse({"delta": chunk.delta})
            if chunk.done:
                message_id = await run_in_threadpool(save)
                yield sse({"done": True, "usage": chunk.usage, "message_id": message_id})
                return
    except ProviderError as exc:
        await run_in_threadpool(save)
        yield sse({"error": str(exc)})
    except Exception:
        logger.exception("Chat stream failed for conversation %s", conversation_id)
        await run_in_threadpool(save)
        yield sse({"error": "Internal error while streaming the response"})
    finally:
        # Client went away (cancellation/GeneratorExit): we can't await here,
        # so save synchronously.
        if not saved:
            save()


@router.post("/stream", dependencies=[Depends(limit_chat)])
async def chat_stream(
    body: ChatStreamRequest, request: Request, session: SessionDep, registry: RegistryDep
) -> StreamingResponse:
    # Validate everything we can before streaming so failures are plain HTTP errors.
    try:
        provider_id, model = split_model_id(body.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    conversation = get_conversation_or_404(session, body.conversation_id)

    await run_in_threadpool(registry.sync, session)
    try:
        provider = registry.get(provider_id)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Persist the user message before calling the model.
    is_first = not any(m.role == "user" for m in list_messages(session, conversation.id))
    session.add(Message(conversation_id=conversation.id, role="user", content=body.message))
    if is_first and conversation.title == DEFAULT_TITLE:
        conversation.title = make_title(body.message)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()

    history = [
        ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
        for m in list_messages(session, conversation.id)
    ]

    return StreamingResponse(
        stream_and_persist(
            request.app.state.engine,
            provider,
            conversation.id,
            body.model_id,
            model,
            history,
            body.params,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

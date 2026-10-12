import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlmodel import Session

from app.auth import ActiveUserDep
from app.db import SessionDep
from app.models import DEFAULT_TITLE, Conversation, Message, utcnow
from app.providers.base import BaseProvider, ProviderError, RefusalError, split_model_id
from app.providers.registry import RegistryDep
from app.rag.service import (
    attached_document_ids,
    build_context,
    embedding_config,
    retrieve,
    sources_payload,
)
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
    engine: Engine,
    conversation_id: str,
    model_id: str,
    content: str,
    sources: list[dict] | None = None,
) -> int | None:
    with Session(engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:  # deleted while streaming
            return None
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            model_id=model_id,
            sources_json=json.dumps(sources) if sources else None,
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
    sources: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Relay provider chunks as normalized SSE and save the assistant reply.

    The reply is saved however the stream ends: on completion, on a provider
    error, or when the client disconnects (Stop button), so partial answers
    survive a refresh. Nothing is saved if no text was produced, or if the
    model declined (a refusal's partial text is discarded).
    """
    parts: list[str] = []
    saved = False

    # Changes if a different model answered (server-side refusal fallback).
    answered_by = model_id

    def save() -> int | None:
        nonlocal saved
        saved = True
        content = "".join(parts)
        if not content:
            return None
        return save_assistant_message(engine, conversation_id, answered_by, content, sources)

    try:
        if sources:
            # Sent first so the citations can be shown while the answer streams.
            yield sse({"sources": sources})
        async for chunk in provider.stream_chat(model, history, params):
            if chunk.delta:
                parts.append(chunk.delta)
                yield sse({"delta": chunk.delta})
            if chunk.done:
                if chunk.served_by:
                    answered_by = f"{provider.id}:{chunk.served_by}"
                message_id = await run_in_threadpool(save)
                done: dict = {"done": True, "usage": chunk.usage, "message_id": message_id}
                if chunk.served_by:
                    done["model_id"] = answered_by
                yield sse(done)
                return
    except RefusalError as exc:
        # A declined reply isn't an answer: drop the partial text and tell the
        # browser to discard what it already showed.
        parts.clear()
        await run_in_threadpool(save)
        yield sse({"error": str(exc), "discard": True})
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
    body: ChatStreamRequest,
    request: Request,
    session: SessionDep,
    registry: RegistryDep,
    user: ActiveUserDep,
) -> StreamingResponse:
    # Validate everything we can before streaming so failures are plain HTTP errors.
    try:
        provider_id, model = split_model_id(body.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    conversation = get_conversation_or_404(session, body.conversation_id, user)

    await run_in_threadpool(registry.sync, session)
    try:
        provider = registry.get(provider_id)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    messages = list_messages(session, conversation.id)
    if body.action == "send":
        # Persist the user message before calling the model.
        is_first = not any(m.role == "user" for m in messages)
        session.add(Message(conversation_id=conversation.id, role="user", content=body.message))
        if is_first and conversation.title == DEFAULT_TITLE:
            conversation.title = make_title(body.message or "")
    elif body.action == "regenerate":
        # Replace the last reply (if there is one) with a new one, possibly from
        # a different model.
        if messages and messages[-1].role == "assistant":
            session.delete(messages.pop())
        if not messages or messages[-1].role != "user":
            raise HTTPException(status_code=400, detail="There's no message to reply to")
    else:  # edit
        target = next((m for m in messages if m.id == body.message_id and m.role == "user"), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Message not found")
        # The conversation continues from the edited message: later turns are dropped.
        for m in messages:
            if m.id > target.id:
                session.delete(m)
        target.content = body.message or ""
        session.add(target)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()

    history = [
        ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
        for m in list_messages(session, conversation.id)
    ]
    if conversation.system_prompt:
        history.insert(0, ChatMessage(role="system", content=conversation.system_prompt))

    # Retrieval: ground the reply in the chat's attached documents, if any.
    sources: list[dict] = []
    document_ids = await run_in_threadpool(attached_document_ids, session, conversation.id, user.id)
    if document_ids:
        question = next((m.content for m in reversed(history) if m.role == "user"), "")
        config = embedding_config(session, request.app.state.settings, request.app.state.cipher)
        found = await retrieve(session, request.app.state.http, config, document_ids, question)
        if found:
            sources = sources_payload(found)
            position = 1 if conversation.system_prompt else 0
            history.insert(position, ChatMessage(role="system", content=build_context(found)))

    return StreamingResponse(
        stream_and_persist(
            request.app.state.engine,
            provider,
            conversation.id,
            body.model_id,
            model,
            history,
            body.params,
            sources,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

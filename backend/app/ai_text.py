"""One-off AI completions outside a chat (notes, channels), streamed as SSE."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import HTTPException
from sqlmodel import Session

from app.catalog import ResolvedModel, resolve_model
from app.models import User
from app.providers.base import BaseProvider, ProviderError
from app.providers.registry import ProviderRegistry
from app.schemas import ChatMessage, ChatParams


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def pick_model(
    session: Session, registry: ProviderRegistry, user: User, model_id: str
) -> tuple[BaseProvider, ResolvedModel]:
    """The provider and model for a menu model ID (custom models included)."""
    resolved = resolve_model(session, user, model_id)
    registry.sync(session)
    try:
        return registry.get(resolved.provider_id), resolved
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def with_persona(resolved: ResolvedModel, messages: list[ChatMessage]) -> list[ChatMessage]:
    """A custom model's own instructions go first."""
    if resolved.persona and resolved.persona.system_prompt:
        return [ChatMessage(role="system", content=resolved.persona.system_prompt), *messages]
    return messages


async def stream_completion(
    provider: BaseProvider,
    model: str,
    messages: list[ChatMessage],
    on_finish: Callable[[str], Awaitable[None]] | None = None,
) -> AsyncIterator[str]:
    """Relay a reply as SSE deltas; `on_finish` gets the text however it ends
    (even partial, when the client goes away)."""
    parts: list[str] = []
    finished = False

    async def finish() -> None:
        nonlocal finished
        if not finished:
            finished = True
            if on_finish is not None:
                await on_finish("".join(parts))

    try:
        async for chunk in provider.stream_chat(model, messages, ChatParams()):
            if chunk.delta:
                parts.append(chunk.delta)
                yield sse({"delta": chunk.delta})
            if chunk.done:
                break
        await finish()
        yield sse({"done": True})
    except ProviderError as exc:
        await finish()
        yield sse({"error": str(exc)})
    finally:
        if not finished and on_finish is not None:
            finished = True
            # Client went away: save what there is without awaiting here.
            asyncio.ensure_future(on_finish("".join(parts)))

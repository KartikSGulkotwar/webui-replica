import json
import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlmodel import Session

from app.app_settings import usable_tools
from app.auth import ActiveUserDep
from app.catalog import resolve_model
from app.db import SessionDep
from app.memory import memory_context, relevant_memories
from app.models import DEFAULT_TITLE, Conversation, Message, utcnow
from app.providers.base import BaseProvider, ProviderError, RefusalError
from app.providers.registry import RegistryDep
from app.rag.service import (
    Source,
    attached_document_ids,
    build_context,
    collection_document_ids,
    embedding_config,
    retrieve,
    sources_payload,
)
from app.ratelimit import limit_chat
from app.routers.conversations import get_conversation_or_404, list_messages
from app.schemas import ChatMessage, ChatParams, ChatStreamRequest, ToolSpec
from app.tools.registry import Tool, ToolContext, ToolOutcome, run_tool
from app.websearch.engines import SearchError, WebSearchConfig, search
from app.websearch.service import make_search_query, web_search_config, web_sources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

TITLE_WORDS = 6
# Tool-calling rounds before the model must answer without tools.
MAX_TOOL_ROUNDS = 5
# How much of a tool's output is shown with the reply (the model gets more).
TRACE_OUTPUT_CHARS = 2000
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
    tools: list[dict] | None = None,
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
            tools_json=json.dumps(tools) if tools else None,
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
    tools: list[Tool] | None = None,
    tool_context: ToolContext | None = None,
    web_search: WebSearchConfig | None = None,
    http: httpx.AsyncClient | None = None,
) -> AsyncIterator[str]:
    """Relay provider chunks as normalized SSE and save the assistant reply.

    With tools, this is an agent loop: when the model asks for tools, they run,
    their results go back to the model, and it continues (up to MAX_TOOL_ROUNDS,
    then one last round without tools so it must answer).

    The reply is saved however the stream ends: on completion, on a provider
    error, or when the client disconnects (Stop button), so partial answers
    survive a refresh. Nothing is saved if nothing was produced, or if the
    model declined (a refusal's partial text is discarded).
    """
    parts: list[str] = []
    trace: list[dict] = []  # tool calls and their results, shown with the reply
    saved = False
    specs = [
        ToolSpec(name=t.id, description=t.description, parameters=t.parameters) for t in tools or []
    ]
    allowed = {t.id for t in tools or []}

    # Changes if a different model answered (server-side refusal fallback).
    answered_by = model_id

    def save() -> int | None:
        nonlocal saved
        saved = True
        content = "".join(parts)
        if not content.strip() and not trace:
            return None
        return save_assistant_message(engine, conversation_id, answered_by, content, sources, trace)

    messages = list(history)
    sources = list(sources or [])
    try:
        if web_search is not None and http is not None:
            # Search before answering; shown as a step like a tool call.
            query = await make_search_query(provider, model, messages)
            step = {"id": "web_search", "name": "web_search", "arguments": {"query": query}}
            yield sse({"tool_call": step})
            question = next((m.content for m in reversed(messages) if m.role == "user"), "")
            found: list[Source] = []
            try:
                results = await search(http, web_search, query)
                found = await web_sources(http, results, question, first_n=len(sources) + 1)
                pages = list(dict.fromkeys(s.url for s in found))
                plural = "" if len(pages) == 1 else "s"
                output = f"Read {len(pages)} page{plural}\n" + "\n".join(p or "" for p in pages)
                error = False
                if not found:
                    output = "No results."
            except SearchError as exc:
                output, error = str(exc), True
            trace.append({**step, "output": output, "error": error})
            yield sse({"tool_result": {"id": step["id"], "output": output, "error": error}})
            lead = next((i for i, m in enumerate(messages) if m.role != "system"), len(messages))
            if found:
                sources += sources_payload(found)
                messages.insert(lead, ChatMessage(role="system", content=build_context(found)))
            else:
                messages.insert(
                    lead,
                    ChatMessage(
                        role="system",
                        content=(
                            "A web search for this message found nothing usable"
                            + (f" ({output})" if error else "")
                            + ". Say so briefly, then answer from what you know."
                        ),
                    ),
                )
        if sources:
            # Sent before the text so the citations can be shown while the answer streams.
            yield sse({"sources": sources})
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            offered = specs if specs and round_number < MAX_TOOL_ROUNDS else None
            round_text: list[str] = []
            final = None
            async for chunk in provider.stream_chat(model, messages, params, offered):
                if chunk.delta:
                    if not round_text and parts:
                        # Text after a tool call starts a new paragraph.
                        parts.append("\n\n")
                        yield sse({"delta": "\n\n"})
                    round_text.append(chunk.delta)
                    parts.append(chunk.delta)
                    yield sse({"delta": chunk.delta})
                if chunk.done:
                    final = chunk
                    break
            if final is None:
                raise ProviderError("The model stopped without finishing its reply")
            if final.served_by:
                answered_by = f"{provider.id}:{final.served_by}"

            if not final.tool_calls:
                message_id = await run_in_threadpool(save)
                if message_id is None and not "".join(parts).strip() and not trace:
                    # Nothing to show (some small models emit a tool call the
                    # server can't parse); say so rather than ending silently.
                    yield sse({"error": "The model returned an empty reply. Try again."})
                    return
                done: dict = {"done": True, "usage": final.usage, "message_id": message_id}
                if final.served_by:
                    done["model_id"] = answered_by
                yield sse(done)
                return

            messages.append(
                ChatMessage(
                    role="assistant",
                    content="".join(round_text),
                    tool_calls=final.tool_calls,
                    provider_state=final.provider_state,
                )
            )
            for call in final.tool_calls:
                yield sse(
                    {"tool_call": {"id": call.id, "name": call.name, "arguments": call.arguments}}
                )
                if call.name in allowed and tool_context is not None:
                    outcome = await run_tool(call.name, call.arguments, tool_context)
                else:
                    outcome = ToolOutcome(f"Tool '{call.name}' isn't enabled for this chat", True)
                shown = outcome.output[:TRACE_OUTPUT_CHARS]
                trace.append(
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "output": shown,
                        "error": outcome.error,
                    }
                )
                yield sse({"tool_result": {"id": call.id, "output": shown, "error": outcome.error}})
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        name=call.name,
                        content=outcome.output,
                        is_error=outcome.error,
                    )
                )
    except RefusalError as exc:
        # A declined reply isn't an answer: drop the partial text and tell the
        # browser to discard what it already showed.
        parts.clear()
        trace.clear()
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
    # A custom model resolves to its base model plus its instructions/knowledge.
    resolved = resolve_model(session, user, body.model_id)
    provider_id, model = resolved.provider_id, resolved.model

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
    # Instructions, most general first: the custom model's, then this chat's.
    prompts = [
        p
        for p in (resolved.persona and resolved.persona.system_prompt, conversation.system_prompt)
        if p
    ]
    for i, prompt in enumerate(prompts):
        history.insert(i, ChatMessage(role="system", content=prompt))
    lead = len(prompts)  # where context blocks go: after the instructions
    question = next((m.content for m in reversed(history) if m.role == "user"), "")

    # Memory: facts the user asked to be remembered, for every chat of theirs.
    memories = await run_in_threadpool(relevant_memories, session, user, question)
    if memories:
        history.insert(lead, ChatMessage(role="system", content=memory_context(memories)))
        lead += 1

    # Retrieval: ground the reply in the chat's attached documents and the
    # custom model's knowledge bases (which belong to the model's creator).
    sources: list[dict] = []
    document_ids = await run_in_threadpool(attached_document_ids, session, conversation.id, user.id)
    if resolved.persona and resolved.knowledge_ids:
        document_ids += await run_in_threadpool(
            collection_document_ids, session, resolved.knowledge_ids, resolved.persona.owner_id
        )
    document_ids = list(dict.fromkeys(document_ids))
    if document_ids:
        config = embedding_config(session, request.app.state.settings, request.app.state.cipher)
        found = await retrieve(session, request.app.state.http, config, document_ids, question)
        if found:
            sources = sources_payload(found)
            history.insert(lead, ChatMessage(role="system", content=build_context(found)))

    # Tools: what this turn asked for plus the custom model's defaults, limited
    # to the ones an admin has enabled (and that are set up).
    settings, cipher = request.app.state.settings, request.app.state.cipher
    wanted = set(body.tools) | set(resolved.tool_ids)
    tools = [t for t in usable_tools(session, settings, cipher) if t.id in wanted]
    search_config = web_search_config(session, settings, cipher)
    if body.web_search and not search_config.enabled:
        raise HTTPException(status_code=400, detail="Web search isn't set up on this server")

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
            tools,
            ToolContext(
                http=request.app.state.http,
                web_search=search_config,
                engine=request.app.state.engine,
                user_id=user.id,
            ),
            search_config if body.web_search else None,
            request.app.state.http,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

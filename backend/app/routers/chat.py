import asyncio
import json
import logging
import random
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlmodel import Session

from app.app_settings import get_admin_settings, usable_tools
from app.auth import ActiveUserDep
from app.catalog import ARENA_MODEL_ID, ResolvedModel, resolve_model
from app.db import SessionDep
from app.images.engines import ImageError, generate
from app.images.service import (
    delete_message_images,
    image_config,
    make_image_prompt,
    store_image,
)
from app.memory import memory_context, relevant_memories
from app.models import DEFAULT_TITLE, Conversation, Message, utcnow
from app.providers.base import BaseProvider, ProviderError, RefusalError, split_model_id
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
MAX_MODELS = 3  # side by side


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


_sse = sse  # stream_and_persist shadows it with a tagging version
_save_lock = threading.Lock()


def save_assistant_message(
    engine: Engine,
    conversation_id: str,
    model_id: str,
    content: str,
    sources: list[dict] | None = None,
    tools: list[dict] | None = None,
    usage: dict | None = None,
    slot: int | None = None,
    blind: bool = False,
    images: list[dict] | None = None,
) -> int | None:
    # Side-by-side replies can finish together; SQLite allows one writer at a time.
    with _save_lock, Session(engine) as session:
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
            prompt_tokens=(usage or {}).get("prompt_tokens"),
            completion_tokens=(usage or {}).get("completion_tokens"),
            slot=slot,
            blind=blind,
            images_json=json.dumps(images) if images else None,
        )
        conversation.updated_at = utcnow()
        session.add(message)
        session.add(conversation)
        session.commit()
        return message.id


@dataclass(frozen=True)
class WebStep:
    """What a web search adds to a reply: its step, the excerpts, and their sources."""

    trace: dict
    context: ChatMessage
    sources: list[dict]


async def web_search_step(
    provider: BaseProvider,
    model: str,
    messages: list[ChatMessage],
    http: httpx.AsyncClient,
    config: WebSearchConfig,
    first_n: int = 1,
) -> AsyncIterator[dict | WebStep]:
    """Search before answering. Yields the step's events as it goes (it shows like
    a tool call), then a WebStep with what the reply should see."""
    query = await make_search_query(provider, model, messages)
    step = {"id": "web_search", "name": "web_search", "arguments": {"query": query}}
    yield {"tool_call": step}
    question = next((m.content for m in reversed(messages) if m.role == "user"), "")
    found: list[Source] = []
    try:
        results = await search(http, config, query)
        found = await web_sources(http, results, question, first_n=first_n)
        pages = list(dict.fromkeys(s.url for s in found))
        plural = "" if len(pages) == 1 else "s"
        output = f"Read {len(pages)} page{plural}\n" + "\n".join(p or "" for p in pages)
        error = False
        if not found:
            output = "No results."
    except SearchError as exc:
        output, error = str(exc), True
    yield {"tool_result": {"id": step["id"], "output": output, "error": error}}
    if found:
        context = ChatMessage(role="system", content=build_context(found))
    else:
        context = ChatMessage(
            role="system",
            content=(
                "A web search for this message found nothing usable"
                + (f" ({output})" if error else "")
                + ". Say so briefly, then answer from what you know."
            ),
        )
    yield WebStep(
        trace={**step, "output": output, "error": error},
        context=context,
        sources=sources_payload(found),
    )


@dataclass(frozen=True)
class ImageStep:
    """What the Image toggle adds to a reply: its step, the image, and a note for the model."""

    trace: dict
    context: ChatMessage
    images: list[dict]


async def image_step(
    provider: BaseProvider,
    model: str,
    messages: list[ChatMessage],
    ctx: ToolContext,
) -> AsyncIterator[dict | ImageStep]:
    """Make an image from the message before the reply. Yields the step's events
    (shown like a tool call), then an ImageStep."""
    prompt = await make_image_prompt(provider, model, messages)
    step = {"id": "generate_image", "name": "generate_image", "arguments": {"prompt": prompt}}
    yield {"tool_call": step}
    images: list[dict] = []
    try:
        if ctx.image_config is None or ctx.engine is None or ctx.user_id is None:
            raise ImageError("Image generation isn't set up")
        image = await generate(ctx.http, ctx.image_config, prompt)
        image_id = await run_in_threadpool(
            store_image,
            ctx.engine,
            ctx.user_id,
            ctx.conversation_id,
            prompt,
            image.data,
            image.mime,
        )
        images = [{"id": image_id, "prompt": prompt}]
        output, error = "Created 1 image", False
    except ImageError as exc:
        output, error = str(exc), True
    yield {"tool_result": {"id": step["id"], "output": output, "error": error}}
    if images:
        yield {"images": images}
        note = (
            f'An image was generated for the user from this prompt: "{prompt}". It is shown '
            "above your reply. Present it in one or two short sentences. You can't see it, so "
            "don't describe details beyond the prompt, and don't add links or markdown images."
        )
    else:
        note = (
            f"Generating the image the user asked for failed ({output}). Tell them briefly "
            "and suggest trying again; don't attempt to draw it in text."
        )
    yield ImageStep(
        trace={**step, "output": output, "error": error},
        context=ChatMessage(role="system", content=note),
        images=images,
    )


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
    *,
    tag: dict | None = None,
    slot: int | None = None,
    blind: bool = False,
    trace_prefix: list[dict] | None = None,
    make_image: bool = False,
    images_prefix: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Relay provider chunks as normalized SSE and save the assistant reply.

    With tools, this is an agent loop: when the model asks for tools, they run,
    their results go back to the model, and it continues (up to MAX_TOOL_ROUNDS,
    then one last round without tools so it must answer).

    The reply is saved however the stream ends: on completion, on a provider
    error, or when the client disconnects (Stop button), so partial answers
    survive a refresh. Nothing is saved if nothing was produced, or if the
    model declined (a refusal's partial text is discarded).

    Side-by-side replies pass `tag` (added to every event, e.g. {"reply": 1}),
    their `slot`, and steps already shown for them (`trace_prefix`).
    """
    parts: list[str] = []
    # Tool calls and their results, shown with the reply.
    trace: list[dict] = list(trace_prefix or [])
    saved = False
    usage: dict[str, int] = {}
    images: list[dict] = list(images_prefix or [])
    tool_images_sent = 0
    # Images the generate_image tool makes are collected per reply.
    if tool_context is not None:
        tool_context = replace(tool_context, images=[])

    def sse(payload: dict) -> str:
        return _sse({**payload, **tag} if tag else payload)

    def add_usage(more: dict | None) -> None:
        for key in ("prompt_tokens", "completion_tokens"):
            if isinstance((more or {}).get(key), int):
                usage[key] = usage.get(key, 0) + more[key]  # type: ignore[index]

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
        if not content.strip() and not trace and not images:
            return None
        return save_assistant_message(
            engine,
            conversation_id,
            answered_by,
            content,
            sources,
            trace,
            usage or None,
            slot,
            blind,
            images,
        )

    messages = list(history)
    sources = list(sources or [])
    try:
        if web_search is not None and http is not None:
            async for item in web_search_step(
                provider, model, messages, http, web_search, first_n=len(sources) + 1
            ):
                if isinstance(item, WebStep):
                    trace.append(item.trace)
                    sources += item.sources
                    lead = next((i for i, m in enumerate(messages) if m.role != "system"), 0)
                    messages.insert(lead, item.context)
                else:
                    yield sse(item)
        if make_image and tool_context is not None:
            async for item in image_step(provider, model, messages, tool_context):
                if isinstance(item, ImageStep):
                    trace.append(item.trace)
                    images += item.images
                    lead = next((i for i, m in enumerate(messages) if m.role != "system"), 0)
                    messages.insert(lead, item.context)
                else:
                    yield sse(item)
        if images_prefix:
            yield sse({"images": images_prefix})
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
            add_usage(final.usage)

            if not final.tool_calls:
                message_id = await run_in_threadpool(save)
                if message_id is None and not "".join(parts).strip() and not trace:
                    # Nothing to show (some small models emit a tool call the
                    # server can't parse); say so rather than ending silently.
                    yield sse({"error": "The model returned an empty reply. Try again."})
                    return
                done: dict = {"done": True, "usage": final.usage, "message_id": message_id}
                if final.served_by and not blind:
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
                made = (tool_context.images or []) if tool_context else []
                if len(made) > tool_images_sent:
                    new = made[tool_images_sent:]
                    tool_images_sent = len(made)
                    images += new
                    yield sse({"images": new})
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


def thread_for(messages: list[Message], model_id: str) -> list[ChatMessage]:
    """The conversation as `model_id` should see it. Where a message got several
    replies side by side, each model continues from its own reply (or the first
    one, if it wasn't among them)."""
    out: list[ChatMessage] = []
    i = 0
    while i < len(messages):
        if messages[i].role != "assistant":
            out.append(ChatMessage(role=messages[i].role, content=messages[i].content))  # type: ignore[arg-type]
            i += 1
            continue
        group = []
        while i < len(messages) and messages[i].role == "assistant":
            group.append(messages[i])
            i += 1
        own = next((m for m in group if m.model_id == model_id), None)
        first = min(group, key=lambda m: (m.slot or 0, m.id or 0))
        out.append(ChatMessage(role="assistant", content=(own or first).content))
    return out


async def merge(streams: list[AsyncIterator[str]]) -> AsyncIterator[str]:
    """Interleave several event streams as their events arrive."""
    queue: asyncio.Queue = asyncio.Queue()
    finished = object()

    async def pump(stream: AsyncIterator[str]) -> None:
        try:
            async for event in stream:
                await queue.put(event)
        finally:
            queue.put_nowait(finished)

    tasks = [asyncio.create_task(pump(s)) for s in streams]
    try:
        remaining = len(tasks)
        while remaining:
            event = await queue.get()
            if event is finished:
                remaining -= 1
            else:
                yield event
        await asyncio.gather(*tasks)  # surfaces unexpected errors
    finally:
        # Client went away: stop the other replies (each saves what it has).
        for task in tasks:
            task.cancel()


@dataclass(frozen=True)
class Target:
    """One model answering the message."""

    model_id: str  # as chosen in the menu
    resolved: ResolvedModel
    provider: BaseProvider


@dataclass(frozen=True)
class Prepared:
    history: list[ChatMessage]
    sources: list[dict]
    tools: list[Tool]


async def side_by_side(
    engine: Engine,
    conversation_id: str,
    targets: list[Target],
    prepared: list[Prepared],
    params: ChatParams,
    tool_context: ToolContext,
    web_search: WebSearchConfig | None,
    http: httpx.AsyncClient,
    blind: bool,
    make_image: bool = False,
) -> AsyncIterator[str]:
    """Several models answer the same message at once. Every event names its
    reply ({"reply": i}); a final untagged {"done": true} ends the turn."""
    yield sse(
        {
            "replies": [
                {"model_id": None if blind else t.model_id, "slot": i}
                for i, t in enumerate(targets)
            ],
            "blind": blind,
        }
    )
    # One web search, shared by every reply.
    step: WebStep | None = None
    if web_search is not None:
        first_n = 1 + max(len(p.sources) for p in prepared)
        lead = targets[0]
        async for item in web_search_step(
            lead.provider, lead.resolved.model, prepared[0].history, http, web_search, first_n
        ):
            if isinstance(item, WebStep):
                step = item
            else:
                for i in range(len(targets)):
                    yield sse({**item, "reply": i})
    # One image, shown with every reply.
    drawn: ImageStep | None = None
    if make_image:
        lead = targets[0]
        async for item in image_step(
            lead.provider, lead.resolved.model, prepared[0].history, tool_context
        ):
            if isinstance(item, ImageStep):
                drawn = item
            elif "images" not in item:  # each reply announces the images itself
                for i in range(len(targets)):
                    yield sse({**item, "reply": i})
    streams = []
    for i, (t, p) in enumerate(zip(targets, prepared, strict=True)):
        history = list(p.history)
        at = next((k for k, m in enumerate(history) if m.role != "system"), 0)
        for added in (step, drawn):
            if added is not None:
                history.insert(at, added.context)
        streams.append(
            stream_and_persist(
                engine,
                t.provider,
                conversation_id,
                t.model_id,
                t.resolved.model,
                history,
                params,
                p.sources + (step.sources if step else []),
                p.tools,
                tool_context,
                tag={"reply": i},
                slot=i,
                blind=blind,
                trace_prefix=[x.trace for x in (step, drawn) if x is not None] or None,
                images_prefix=drawn.images if drawn else None,
            )
        )
    async for event in merge(streams):
        yield event
    yield sse({"done": True})


def arena_pool(session: Session, settings, registry) -> list[str]:
    """Arena models an admin chose whose providers are working."""
    pool = []
    for model_id in get_admin_settings(session, settings).arena_models:
        try:
            registry.get(split_model_id(model_id)[0])
        except (ProviderError, ValueError):
            continue
        pool.append(model_id)
    return pool


@router.post("/stream", dependencies=[Depends(limit_chat)])
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    session: SessionDep,
    registry: RegistryDep,
    user: ActiveUserDep,
) -> StreamingResponse:
    # Validate everything we can before streaming so failures are plain HTTP errors.
    settings, cipher = request.app.state.settings, request.app.state.cipher
    conversation = get_conversation_or_404(session, body.conversation_id, user)
    await run_in_threadpool(registry.sync, session)

    # Who answers: one model, several side by side, or two hidden arena models.
    blind = body.model_id == ARENA_MODEL_ID
    if blind:
        pool = arena_pool(session, settings, registry)
        if len(pool) < 2:
            raise HTTPException(
                status_code=400, detail="The arena needs at least two models (Admin → Evaluations)"
            )
        model_ids = random.sample(pool, 2)
    else:
        model_ids = list(dict.fromkeys([body.model_id, *body.model_ids]))
        if ARENA_MODEL_ID in model_ids:
            raise HTTPException(status_code=422, detail="The arena can't be combined with models")
        if len(model_ids) > MAX_MODELS:
            raise HTTPException(status_code=422, detail=f"Choose at most {MAX_MODELS} models")
    if body.message_id is not None and body.action == "regenerate" and len(model_ids) > 1:
        raise HTTPException(status_code=422, detail="Regenerate one reply with one model")
    targets: list[Target] = []
    for model_id in model_ids:
        # A custom model resolves to its base model plus its instructions/knowledge.
        # Arena models were chosen by an admin, so they may be hidden from the menu.
        resolved = (
            ResolvedModel(*split_model_id(model_id))
            if blind
            else resolve_model(session, user, model_id)
        )
        try:
            provider = registry.get(resolved.provider_id)
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        targets.append(Target(model_id, resolved, provider))

    messages = list_messages(session, conversation.id)
    slot = None  # regenerating one of several replies keeps its column
    if body.action == "send":
        # Persist the user message before calling the model.
        is_first = not any(m.role == "user" for m in messages)
        session.add(Message(conversation_id=conversation.id, role="user", content=body.message))
        if is_first and conversation.title == DEFAULT_TITLE:
            conversation.title = make_title(body.message or "")
    elif body.action == "regenerate":
        last_user = max((m.id or 0 for m in messages if m.role == "user"), default=None)
        if last_user is None:
            raise HTTPException(status_code=400, detail="There's no message to reply to")
        if body.message_id is not None:
            # Replace one reply to the last message (the others stay).
            reply = next(
                (m for m in messages if m.id == body.message_id and m.role == "assistant"), None
            )
            if reply is None or (reply.id or 0) < last_user:
                raise HTTPException(status_code=404, detail="Reply not found")
            if reply.blind:
                raise HTTPException(status_code=400, detail="Arena replies can't be regenerated")
            slot = reply.slot
            delete_message_images(session, [reply])
            session.delete(reply)
        else:
            # Replace every reply to the last message, possibly with other models.
            for m in messages:
                if m.role == "assistant" and (m.id or 0) > last_user:
                    delete_message_images(session, [m])
                    session.delete(m)
    else:  # edit
        target = next((m for m in messages if m.id == body.message_id and m.role == "user"), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Message not found")
        # The conversation continues from the edited message: later turns are dropped.
        for m in messages:
            if m.id > target.id:
                delete_message_images(session, [m])
                session.delete(m)
        target.content = body.message or ""
        session.add(target)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()

    # Everything up to the message being answered (other replies to it excluded).
    stored = list_messages(session, conversation.id)
    last = max(i for i, m in enumerate(stored) if m.role == "user")
    stored, question = stored[: last + 1], stored[last].content

    # Shared by every model: memory, attached documents, tools, web search.
    memories = await run_in_threadpool(relevant_memories, session, user, question)
    attached = await run_in_threadpool(attached_document_ids, session, conversation.id, user.id)
    embeddings = embedding_config(session, settings, cipher)
    available_tools = usable_tools(session, settings, cipher)
    search_config = web_search_config(session, settings, cipher)
    if body.web_search and not search_config.enabled:
        raise HTTPException(status_code=400, detail="Web search isn't set up on this server")
    images_config = image_config(session, settings, cipher)
    if body.image_generation and not images_config.enabled:
        raise HTTPException(status_code=400, detail="Image generation isn't set up on this server")
    http: httpx.AsyncClient = request.app.state.http

    async def prepare(t: Target) -> Prepared:
        persona = t.resolved.persona
        # Instructions, most general first: the custom model's, then this chat's;
        # then context blocks.
        prefix = [
            ChatMessage(role="system", content=p)
            for p in (persona and persona.system_prompt, conversation.system_prompt)
            if p
        ]
        if memories:
            prefix.append(ChatMessage(role="system", content=memory_context(memories)))
        # Retrieval: the chat's attached documents and the custom model's
        # knowledge bases (which belong to the model's creator).
        document_ids = list(attached)
        if persona and t.resolved.knowledge_ids:
            document_ids += await run_in_threadpool(
                collection_document_ids, session, t.resolved.knowledge_ids, persona.owner_id
            )
        sources: list[dict] = []
        if document_ids:
            found = await retrieve(
                session, http, embeddings, list(dict.fromkeys(document_ids)), question
            )
            if found:
                sources = sources_payload(found)
                prefix.append(ChatMessage(role="system", content=build_context(found)))
        # Tools: what this turn asked for plus the custom model's defaults,
        # limited to the ones an admin has enabled (and that are set up).
        wanted = set(body.tools) | set(t.resolved.tool_ids)
        tools = [x for x in available_tools if x.id in wanted]
        return Prepared(prefix + thread_for(stored, t.model_id), sources, tools)

    tool_context = ToolContext(
        http=http,
        web_search=search_config,
        engine=request.app.state.engine,
        user_id=user.id,
        conversation_id=conversation.id,
        image_config=images_config,
    )
    web = search_config if body.web_search else None
    if len(targets) == 1:
        t = targets[0]
        p = await prepare(t)
        stream = stream_and_persist(
            request.app.state.engine,
            t.provider,
            conversation.id,
            t.model_id,
            t.resolved.model,
            p.history,
            body.params,
            p.sources,
            p.tools,
            tool_context,
            web,
            http,
            slot=slot,
            make_image=body.image_generation,
        )
    else:
        stream = side_by_side(
            request.app.state.engine,
            conversation.id,
            targets,
            [await prepare(t) for t in targets],
            body.params,
            tool_context,
            web,
            http,
            blind,
            body.image_generation,
        )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

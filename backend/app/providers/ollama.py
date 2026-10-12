import json
from collections.abc import AsyncIterator
from typing import ClassVar

import httpx

from app.providers.base import (
    STREAM_TIMEOUT,
    BaseProvider,
    ProviderError,
    describe_http_error,
    error_from_response,
)
from app.schemas import (
    ChatMessage,
    ChatParams,
    ModelInfo,
    ProviderKind,
    StreamChunk,
    ToolCall,
    ToolSpec,
)


def parse_ollama_line(line: str) -> StreamChunk | None:
    """Parse one NDJSON line from Ollama's /api/chat stream."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Malformed stream line from Ollama: {line[:100]}") from exc
    if "error" in data:
        raise ProviderError(str(data["error"]))
    if data.get("done"):
        usage = {}
        if "prompt_eval_count" in data:
            usage["prompt_tokens"] = data["prompt_eval_count"]
        if "eval_count" in data:
            usage["completion_tokens"] = data["eval_count"]
        if usage:
            usage["total_tokens"] = sum(usage.values())
        # The final line can still carry trailing content.
        delta = (data.get("message") or {}).get("content", "")
        return StreamChunk(delta=delta, done=True, usage=usage or None)
    message = data.get("message") or {}
    delta = message.get("content", "")
    calls = message.get("tool_calls")
    if calls:
        # Ollama sends whole tool calls (no IDs) in a regular chunk.
        return StreamChunk(
            delta=delta,
            tool_calls=[
                ToolCall(
                    id=f"call_{i}",
                    name=(c.get("function") or {}).get("name", ""),
                    arguments=(c.get("function") or {}).get("arguments", {}),
                )
                for i, c in enumerate(calls)
            ],
        )
    return StreamChunk(delta=delta) if delta else None


def to_wire(messages: list[ChatMessage]) -> list[dict]:
    """Our turns in Ollama /api/chat format, including tool turns."""
    out: list[dict] = []
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content,
                    "tool_calls": [
                        {
                            "function": {
                                "name": c.name,
                                "arguments": c.arguments if isinstance(c.arguments, dict) else {},
                            }
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        elif m.role == "tool":
            out.append({"role": "tool", "content": m.content, "tool_name": m.name})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


# Embedding-only models (for document search) can't chat. Ollama's tag list
# doesn't say so directly, so go by name and model family.
EMBEDDING_FAMILIES = {"bert", "nomic-bert"}
EMBEDDING_MARKERS = ("embed", "minilm", "bge-")


def is_chat_model(model: dict) -> bool:
    name = model.get("name", "").lower()
    details = model.get("details") or {}
    families = {details.get("family") or "", *(details.get("families") or [])}
    if families & EMBEDDING_FAMILIES:
        return False
    return not any(marker in name for marker in EMBEDDING_MARKERS)


class OllamaProvider(BaseProvider):
    kind: ClassVar[ProviderKind] = "ollama"

    async def list_models(self) -> list[ModelInfo]:
        data = await self._get_json("/api/tags")
        names = [m["name"] for m in data.get("models", []) if m.get("name") and is_chat_model(m)]
        return [self._model_info(n) for n in sorted(names)]

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: ChatParams,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        options: dict = {}
        if params.temperature is not None:
            options["temperature"] = params.temperature
        if params.max_tokens is not None:
            options["num_predict"] = params.max_tokens
        body = {
            "model": model,
            "messages": to_wire(messages),
            "stream": True,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        if options:
            body["options"] = options

        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=body, timeout=STREAM_TIMEOUT
            ) as resp:
                if resp.status_code >= 400:
                    raise error_from_response(resp, await resp.aread())
                calls: list[ToolCall] = []
                async for line in resp.aiter_lines():
                    chunk = parse_ollama_line(line)
                    if chunk is None:
                        continue
                    if chunk.tool_calls and not chunk.done:
                        # Renumber IDs so calls from several chunks stay unique.
                        calls += [
                            c.model_copy(update={"id": f"call_{len(calls) + i}"})
                            for i, c in enumerate(chunk.tool_calls)
                        ]
                        chunk = chunk.model_copy(update={"tool_calls": None})
                        if not chunk.delta:
                            continue
                    if chunk.done and calls:
                        chunk = chunk.model_copy(update={"tool_calls": calls})
                    yield chunk
                    if chunk.done:
                        return
        except httpx.HTTPError as exc:
            raise ProviderError(describe_http_error(exc, self.base_url)) from exc
        raise ProviderError("Ollama stream ended unexpectedly")

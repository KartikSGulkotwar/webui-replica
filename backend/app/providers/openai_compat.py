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

DONE = object()  # sentinel for the "[DONE]" terminator

# /models on OpenAI-style APIs also lists speech, embedding, image, and safety
# models, which fail on /chat/completions. Hide them from the chat model menu.
NON_CHAT_MARKERS = (
    "whisper",
    "transcribe",
    "tts",
    "orpheus",
    "embed",
    "moderation",
    "guard",
    "dall-e",
    "gpt-image",
)


def is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in NON_CHAT_MARKERS)


def parse_sse_line(line: str) -> StreamChunk | object | None:
    """Parse one line of an OpenAI-style SSE stream.

    Returns a StreamChunk, the DONE sentinel, or None for lines that carry nothing
    (blank lines, comments, keep-alives, role-only deltas)."""
    line = line.strip()
    if not line or line.startswith(":") or not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if payload == "[DONE]":
        return DONE
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Malformed stream event: {payload[:100]}") from exc
    if "error" in data:
        err = data["error"]
        raise ProviderError(str(err.get("message", err)) if isinstance(err, dict) else str(err))

    choices = data.get("choices") or []
    delta = ""
    fragments = None
    if choices:
        choice_delta = choices[0].get("delta") or {}
        delta = choice_delta.get("content") or ""
        fragments = choice_delta.get("tool_calls") or None
    usage = data.get("usage")
    if usage or fragments:
        # Usage arrives on its own (choices empty) when stream_options.include_usage is set.
        return StreamChunk(delta=delta, usage=usage or None, provider_state=fragments)
    return StreamChunk(delta=delta) if delta else None


def to_wire(messages: list[ChatMessage]) -> list[dict]:
    """Our turns in OpenAI chat-completions format, including tool turns."""
    out: list[dict] = []
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        elif m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def assemble_tool_calls(parts: dict[int, dict]) -> list[ToolCall]:
    """Join streamed tool-call fragments (keyed by index) into whole calls."""
    calls = []
    for index in sorted(parts):
        part = parts[index]
        try:
            arguments = json.loads(part["arguments"] or "{}")
        except json.JSONDecodeError:
            arguments = part["arguments"]  # the tool reports it as invalid
        calls.append(
            ToolCall(id=part["id"] or f"call_{index}", name=part["name"], arguments=arguments)
        )
    return calls


class OpenAICompatProvider(BaseProvider):
    kind: ClassVar[ProviderKind] = "openai_compat"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def list_models(self) -> list[ModelInfo]:
        data = await self._get_json("/models", headers=self._headers())
        ids = [m["id"] for m in data.get("data", []) if m.get("id") and is_chat_model(m["id"])]
        return [self._model_info(i) for i in sorted(ids)]

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: ChatParams,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        body: dict = {
            "model": model,
            "messages": to_wire(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
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
        if params.temperature is not None:
            body["temperature"] = params.temperature
        if params.max_tokens is not None:
            body["max_tokens"] = params.max_tokens

        usage: dict | None = None
        calls: dict[int, dict] = {}
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
                headers=self._headers(),
                timeout=STREAM_TIMEOUT,
            ) as resp:
                if resp.status_code >= 400:
                    raise error_from_response(resp, await resp.aread())
                async for line in resp.aiter_lines():
                    event = parse_sse_line(line)
                    if event is None:
                        continue
                    if event is DONE:
                        break
                    assert isinstance(event, StreamChunk)
                    if event.usage:
                        usage = event.usage
                    for fragment in event.provider_state or []:
                        part = calls.setdefault(
                            fragment.get("index", 0), {"id": None, "name": "", "arguments": ""}
                        )
                        part["id"] = fragment.get("id") or part["id"]
                        function = fragment.get("function") or {}
                        part["name"] += function.get("name") or ""
                        args = function.get("arguments")
                        # Usually a string built up in pieces; some servers send an object.
                        part["arguments"] += (
                            args if isinstance(args, str) else json.dumps(args or {})
                        )
                    if event.delta:
                        yield StreamChunk(delta=event.delta)
        except httpx.HTTPError as exc:
            raise ProviderError(describe_http_error(exc, self.base_url)) from exc
        # Some servers close without "[DONE]"; treat a clean close as completion.
        yield StreamChunk(done=True, usage=usage, tool_calls=assemble_tool_calls(calls) or None)

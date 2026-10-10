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
from app.schemas import ChatMessage, ChatParams, ModelInfo, ProviderKind, StreamChunk

DONE = object()  # sentinel for the "[DONE]" terminator


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
    if choices:
        delta = (choices[0].get("delta") or {}).get("content") or ""
    usage = data.get("usage")
    if usage:
        # Usage arrives on its own (choices empty) when stream_options.include_usage is set.
        return StreamChunk(delta=delta, usage=usage)
    return StreamChunk(delta=delta) if delta else None


class OpenAICompatProvider(BaseProvider):
    kind: ClassVar[ProviderKind] = "openai_compat"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def list_models(self) -> list[ModelInfo]:
        data = await self._get_json("/models", headers=self._headers())
        ids = [m["id"] for m in data.get("data", []) if m.get("id")]
        return [self._model_info(i) for i in sorted(ids)]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage], params: ChatParams
    ) -> AsyncIterator[StreamChunk]:
        body: dict = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if params.temperature is not None:
            body["temperature"] = params.temperature
        if params.max_tokens is not None:
            body["max_tokens"] = params.max_tokens

        usage: dict | None = None
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
                    if event.delta:
                        yield StreamChunk(delta=event.delta)
        except httpx.HTTPError as exc:
            raise ProviderError(describe_http_error(exc, self.base_url)) from exc
        # Some servers close without "[DONE]"; treat a clean close as completion.
        yield StreamChunk(done=True, usage=usage)

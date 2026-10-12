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
    delta = (data.get("message") or {}).get("content", "")
    return StreamChunk(delta=delta) if delta else None


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
        self, model: str, messages: list[ChatMessage], params: ChatParams
    ) -> AsyncIterator[StreamChunk]:
        options: dict = {}
        if params.temperature is not None:
            options["temperature"] = params.temperature
        if params.max_tokens is not None:
            options["num_predict"] = params.max_tokens
        body = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        if options:
            body["options"] = options

        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=body, timeout=STREAM_TIMEOUT
            ) as resp:
                if resp.status_code >= 400:
                    raise error_from_response(resp, await resp.aread())
                async for line in resp.aiter_lines():
                    chunk = parse_ollama_line(line)
                    if chunk is None:
                        continue
                    yield chunk
                    if chunk.done:
                        return
        except httpx.HTTPError as exc:
            raise ProviderError(describe_http_error(exc, self.base_url)) from exc
        raise ProviderError("Ollama stream ended unexpectedly")

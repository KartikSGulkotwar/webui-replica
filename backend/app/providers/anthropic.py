"""Native Anthropic (Claude) provider, using the official Python SDK."""

from collections.abc import AsyncIterator
from typing import Any, ClassVar
from urllib.parse import urlparse

import anthropic
import httpx

from app.providers.base import BaseProvider, ProviderError, RefusalError
from app.schemas import ChatMessage, ChatParams, ModelInfo, ProviderKind, StreamChunk

DEFAULT_BASE_URL = "https://api.anthropic.com"
# Streaming, so a generous ceiling doesn't risk HTTP timeouts; capped per model
# at the max_tokens the Models API reports.
DEFAULT_MAX_TOKENS = 64_000
# Models whose safety classifiers can decline; on the Claude API, opt into
# server-side fallback so a decline is retried on Anthropic's recommended model.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def make_client(api_key: str | None, base_url: str) -> anthropic.AsyncAnthropic:
    """Separate so tests can swap in a mock transport."""
    return anthropic.AsyncAnthropic(api_key=api_key or "", base_url=base_url, timeout=300.0)


def api_message(exc: anthropic.APIStatusError) -> str:
    """The human-readable message from Anthropic's error body, not the raw dump."""
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else body
    return str(error.get("message") or exc.message)


def describe_error(exc: anthropic.AnthropicError) -> str:
    # Most specific first: retryable vs. fix-your-settings errors read differently.
    if isinstance(exc, anthropic.AuthenticationError):
        return "Invalid Anthropic API key"
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This Anthropic API key isn't allowed to use that model"
    if isinstance(exc, anthropic.NotFoundError):
        return "Model not found on Anthropic"
    if isinstance(exc, anthropic.RateLimitError):
        return "Anthropic rate limit reached. Please wait a moment and try again."
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code == 529:
            return "Anthropic is overloaded right now. Please try again shortly."
        return f"Anthropic API error ({exc.status_code}): {api_message(exc)}"
    if isinstance(exc, anthropic.APITimeoutError):
        return "Timed out talking to Anthropic"
    if isinstance(exc, anthropic.APIConnectionError):
        return "Cannot connect to Anthropic"
    return str(exc)


def split_system(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, str]]]:
    """Claude takes the system prompt as a top-level field, not a message."""
    system = "\n\n".join(m.content for m in messages if m.role == "system") or None
    rest = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return system, rest


def usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    cached = (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
    prompt = (usage.input_tokens or 0) + cached
    completion = usage.output_tokens or 0
    result = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if usage.cache_read_input_tokens:
        result["cache_read_tokens"] = usage.cache_read_input_tokens
    return result


class AnthropicProvider(BaseProvider):
    kind: ClassVar[ProviderKind] = "anthropic"

    def __init__(
        self,
        id: str,
        name: str,
        base_url: str,
        client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        super().__init__(id, name, base_url or DEFAULT_BASE_URL, client, api_key)
        # The SDK brings its own HTTP stack (httpx2), so the shared httpx client
        # isn't used here.
        self._sdk = make_client(api_key, self.base_url)
        self._max_tokens: dict[str, int] = {}

    @property
    def is_claude_api(self) -> bool:
        return urlparse(self.base_url).hostname == "api.anthropic.com"

    async def list_models(self) -> list[ModelInfo]:
        try:
            models = [m async for m in self._sdk.models.list()]
        except anthropic.AnthropicError as exc:
            raise ProviderError(describe_error(exc)) from exc
        for m in models:
            if getattr(m, "max_tokens", None):
                self._max_tokens[m.id] = m.max_tokens
        return [self._model_info(m.id) for m in sorted(models, key=lambda m: m.id)]

    async def _max_tokens_for(self, model: str, requested: int | None) -> int:
        if model not in self._max_tokens:
            try:
                info = await self._sdk.models.retrieve(model)
                if getattr(info, "max_tokens", None):
                    self._max_tokens[model] = info.max_tokens
            except anthropic.AnthropicError:
                pass  # unknown limit: the default is safe for current models
        cap = self._max_tokens.get(model, DEFAULT_MAX_TOKENS)
        return min(requested or DEFAULT_MAX_TOKENS, cap)

    async def stream_chat(
        self, model: str, messages: list[ChatMessage], params: ChatParams
    ) -> AsyncIterator[StreamChunk]:
        system, history = split_system(messages)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": await self._max_tokens_for(model, params.max_tokens),
            "messages": history,
            # Each turn resends the whole chat; caching the prefix makes that cheap.
            "cache_control": {"type": "ephemeral"},
        }
        if system:
            request["system"] = system
        # params.temperature is intentionally not sent: current Claude models
        # reject non-default sampling parameters.

        use_fallback = self.is_claude_api and model in FALLBACK_MODELS
        try:
            if use_fallback:
                stream_cm = self._sdk.beta.messages.stream(
                    **request, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                stream_cm = self._sdk.messages.stream(**request)
            async with stream_cm as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        if event.delta.text:
                            yield StreamChunk(delta=event.delta.text)
                final = await stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise ProviderError(describe_error(exc)) from exc

        if final.stop_reason == "refusal":
            details = getattr(final, "stop_details", None)
            category = getattr(details, "category", None)
            raise RefusalError(
                "Claude declined to answer this request"
                + (f" ({category} safety policy)" if category else "")
                + ". Try rephrasing, or pick a different model."
            )
        served_by = final.model if final.model and final.model != model else None
        yield StreamChunk(done=True, usage=usage_dict(final.usage), served_by=served_by)

"""Embedding engines: an Ollama server or any OpenAI-compatible /embeddings API."""

from dataclasses import dataclass

import httpx

from app.providers.base import ProviderError, describe_http_error, error_from_response

BATCH = 64
TIMEOUT = httpx.Timeout(120.0, connect=5.0)


@dataclass(frozen=True)
class EmbeddingConfig:
    engine: str  # "" (keyword search only) | "ollama" | "openai"
    base_url: str
    model: str
    api_key: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.engine and self.base_url and self.model)

    @property
    def key(self) -> str:
        """Identifies the vector space; chunks embedded differently aren't comparable."""
        return f"{self.engine}:{self.model}"


async def embed(
    http: httpx.AsyncClient, config: EmbeddingConfig, texts: list[str]
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        vectors.extend(await _embed_batch(http, config, texts[i : i + BATCH]))
    return vectors


async def _embed_batch(
    http: httpx.AsyncClient, config: EmbeddingConfig, texts: list[str]
) -> list[list[float]]:
    base = config.base_url.rstrip("/")
    if config.engine == "ollama":
        url, body, headers = f"{base}/api/embed", {"model": config.model, "input": texts}, {}
    else:
        url = f"{base}/embeddings"
        body = {"model": config.model, "input": texts}
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    try:
        resp = await http.post(url, json=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise ProviderError(describe_http_error(exc, base)) from exc
    if resp.status_code >= 400:
        raise error_from_response(resp)
    data = resp.json()
    if config.engine == "ollama":
        vectors = data.get("embeddings")
    else:
        vectors = [d["embedding"] for d in sorted(data.get("data", []), key=lambda d: d["index"])]
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ProviderError("The embedding service returned an unexpected response")
    return vectors

"""Search engines: each turns a query into (title, url, snippet) results."""

import html
import logging
import re
import time
from dataclasses import dataclass

import httpx
from fastapi.concurrency import run_in_threadpool

ENGINES = {
    "duckduckgo": "DuckDuckGo (no key)",
    "searxng": "SearXNG",
    "brave": "Brave Search",
    "tavily": "Tavily",
}
NEEDS_KEY = {"brave", "tavily"}
NEEDS_URL = {"searxng"}
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
DDGS_ATTEMPTS = 3  # its backends rotate and sometimes all come back empty
DDGS_RETRY_PAUSE = 0.7  # seconds, doubled after each empty attempt

# ddgs's HTTP client logs every request at INFO.
logging.getLogger("primp").setLevel(logging.WARNING)


class SearchError(Exception):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class WebSearchConfig:
    engine: str  # "" = off
    base_url: str = ""
    api_key: str | None = None
    result_count: int = 3

    @property
    def enabled(self) -> bool:
        if self.engine not in ENGINES:
            return False
        if self.engine in NEEDS_URL and not self.base_url:
            return False
        return not (self.engine in NEEDS_KEY and not self.api_key)


def _plain(text: str | None) -> str:
    """Snippets can contain HTML highlighting (<strong>) and entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def _clean(results: list[SearchResult], count: int) -> list[SearchResult]:
    seen: set[str] = set()
    out = []
    for r in results:
        if not r.url.startswith(("http://", "https://")) or r.url in seen:
            continue
        seen.add(r.url)
        out.append(SearchResult(_plain(r.title) or r.url, r.url, _plain(r.snippet)))
    return out[:count]


def _ddgs(query: str, count: int) -> list[SearchResult]:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException

    rows: list[dict] = []
    for attempt in range(DDGS_ATTEMPTS):
        if attempt:
            time.sleep(DDGS_RETRY_PAUSE * 2 ** (attempt - 1))  # runs in a worker thread
        try:
            rows = DDGS(timeout=10).text(query, max_results=count)
        except DDGSException as exc:
            if "no results" not in str(exc).lower():
                raise SearchError(f"DuckDuckGo search failed: {exc}") from exc
        except Exception as exc:  # network errors from its own HTTP client
            raise SearchError(f"DuckDuckGo search failed: {exc.__class__.__name__}") from exc
        if rows:
            break
    return [SearchResult(r.get("title", ""), r.get("href", ""), r.get("body", "")) for r in rows]


async def _json(resp: httpx.Response, engine: str) -> dict:
    if resp.status_code in (401, 403):
        raise SearchError(f"{engine} rejected the API key")
    if resp.status_code == 429:
        raise SearchError(f"{engine} rate limit reached; try again later")
    if resp.status_code >= 400:
        raise SearchError(f"{engine} returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SearchError(f"{engine} returned something that isn't JSON") from exc


async def search(
    http: httpx.AsyncClient, config: WebSearchConfig, query: str, count: int | None = None
) -> list[SearchResult]:
    count = count or config.result_count
    query = query.strip()[:400]
    if not config.enabled:
        raise SearchError("Web search isn't set up")
    try:
        if config.engine == "duckduckgo":
            results = await run_in_threadpool(_ddgs, query, count + 2)
        elif config.engine == "searxng":
            resp = await http.get(
                f"{config.base_url}/search",
                params={"q": query, "format": "json"},
                timeout=TIMEOUT,
            )
            data = await _json(resp, "SearXNG")
            results = [
                SearchResult(r.get("title", ""), r.get("url", ""), r.get("content", ""))
                for r in data.get("results", [])
            ]
        elif config.engine == "brave":
            resp = await http.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": min(count + 2, 20)},
                headers={
                    "X-Subscription-Token": config.api_key or "",
                    "Accept": "application/json",
                },
                timeout=TIMEOUT,
            )
            data = await _json(resp, "Brave Search")
            results = [
                SearchResult(r.get("title", ""), r.get("url", ""), r.get("description", ""))
                for r in (data.get("web") or {}).get("results", [])
            ]
        else:  # tavily
            resp = await http.post(
                "https://api.tavily.com/search",
                json={"query": query, "max_results": min(count + 2, 20)},
                headers={"Authorization": f"Bearer {config.api_key}"},
                timeout=TIMEOUT,
            )
            data = await _json(resp, "Tavily")
            results = [
                SearchResult(r.get("title", ""), r.get("url", ""), r.get("content", ""))
                for r in data.get("results", [])
            ]
    except httpx.TimeoutException as exc:
        raise SearchError("The search engine took too long to respond") from exc
    except httpx.HTTPError as exc:
        raise SearchError(f"Couldn't reach the search engine: {exc.__class__.__name__}") from exc
    return _clean(results, count)

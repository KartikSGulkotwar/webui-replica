"""Web search for chat: settings, the search query, and pages turned into citable sources."""

import asyncio
import json
import logging

import httpx
from sqlmodel import Session

from app.config import Settings
from app.crypto import EncryptionError, KeyCipher
from app.models import AppSetting
from app.providers.base import BaseProvider, ProviderError
from app.rag.chunk import chunk_pages
from app.rag.extract import Page
from app.rag.search import Candidate, bm25_rank
from app.rag.service import Source
from app.schemas import ChatMessage, ChatParams
from app.tools.web import FetchError, fetch_text
from app.websearch.engines import SearchResult, WebSearchConfig

logger = logging.getLogger(__name__)

SETTINGS_KEY = "web_search"
PAGE_CHARS = 20_000  # read this much of each result page
PAGE_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
TOP_K = 5  # passages given to the model
PER_PAGE = 2  # at most this many from one page, so several sites get cited
QUERY_TIMEOUT = 20.0
MAX_QUERY_CHARS = 200


# --- settings ----------------------------------------------------------------------


def load_web_search_settings(session: Session, settings: Settings) -> dict:
    """Stored admin settings (api key encrypted), falling back to env defaults."""
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is not None:
        return json.loads(row.value)
    return {
        "engine": settings.web_search_engine,
        "base_url": settings.web_search_base_url,
        "result_count": settings.web_search_result_count,
        "api_key_encrypted": None,
        "env_api_key": bool(settings.web_search_api_key),
    }


def save_web_search_settings(session: Session, values: dict) -> None:
    row = session.get(AppSetting, SETTINGS_KEY) or AppSetting(key=SETTINGS_KEY, value="{}")
    row.value = json.dumps(values)
    session.add(row)
    session.commit()


def web_search_config(session: Session, settings: Settings, cipher: KeyCipher) -> WebSearchConfig:
    stored = load_web_search_settings(session, settings)
    api_key = None
    if stored.get("api_key_encrypted"):
        try:
            api_key = cipher.decrypt(stored["api_key_encrypted"])
        except EncryptionError:
            logger.warning("Web search API key can't be decrypted; using no key")
    elif stored.get("env_api_key"):
        api_key = settings.web_search_api_key
    return WebSearchConfig(
        engine=stored.get("engine") or "",
        base_url=stored.get("base_url") or "",
        api_key=api_key,
        result_count=int(stored.get("result_count") or 3),
    )


# --- query -------------------------------------------------------------------------


def _clean_query(text: str) -> str:
    line = next((ln.strip() for ln in text.strip().splitlines() if ln.strip()), "")
    return line.strip("\"'` ").removeprefix("Query:").strip()[:MAX_QUERY_CHARS]


async def make_search_query(provider: BaseProvider, model: str, history: list[ChatMessage]) -> str:
    """What to search for. A first message is searched as written; a follow-up
    ("and in 2024?") is rewritten by the model into a standalone query."""
    turns = [m for m in history if m.role in ("user", "assistant") and m.content.strip()]
    question = next((m.content for m in reversed(turns) if m.role == "user"), "")
    if len([m for m in turns if m.role == "user"]) <= 1:
        return question.strip()[:400]
    transcript = "\n".join(f"{m.role}: {m.content[:1000]}" for m in turns[-6:])
    prompt = [
        ChatMessage(
            role="system",
            content=(
                "You turn the last message of a conversation into a web search query. "
                "Don't answer the question. Reply with the query only: a few keywords, "
                "under 12 words, that make sense without the rest of the conversation."
            ),
        ),
        ChatMessage(
            role="user",
            content=f"<conversation>\n{transcript}\n</conversation>\n\nSearch query:",
        ),
    ]

    async def ask() -> str:
        parts = []
        async for chunk in provider.stream_chat(model, prompt, ChatParams(temperature=0)):
            parts.append(chunk.delta)
            if chunk.done:
                break
        return "".join(parts)

    try:
        query = _clean_query(await asyncio.wait_for(ask(), QUERY_TIMEOUT))
    except (ProviderError, TimeoutError) as exc:
        logger.info("Search query rewrite failed, searching the message as written: %s", exc)
        query = ""
    return query or question.strip()[:400]


# --- results -> sources ------------------------------------------------------------


async def _read(http: httpx.AsyncClient, result: SearchResult) -> tuple[str, str]:
    """(url, text) of a result page; the search snippet if the page can't be read."""
    try:
        url, text = await fetch_text(http, result.url, max_chars=PAGE_CHARS, timeout=PAGE_TIMEOUT)
    except FetchError as exc:
        logger.info("Using the snippet for %s: %s", result.url, exc)
        return result.url, result.snippet
    return url, text.removesuffix("\n…(truncated)") or result.snippet


async def web_sources(
    http: httpx.AsyncClient,
    results: list[SearchResult],
    question: str,
    first_n: int = 1,
) -> list[Source]:
    """The passages from the result pages that best match the question."""
    pages = await asyncio.gather(*(_read(http, r) for r in results))
    candidates: list[Candidate] = []
    owner: dict[int, int] = {}  # candidate id -> result index
    for i, (_, text) in enumerate(pages):
        for chunk in chunk_pages([Page(None, text)]):
            owner[len(candidates)] = i
            candidates.append(Candidate(len(candidates), chunk.text))
    ranked = bm25_rank(question, candidates)
    # Pages that share no words with the question still count: lead with their
    # first passage so a reply always has the top results to work from.
    for i in range(len(results)):
        first = next((cid for cid, r in owner.items() if r == i), None)
        if first is not None and first not in ranked:
            ranked.append(first)
    picked: list[int] = []
    per_page: dict[int, int] = {}
    for cid in ranked:
        page = owner[cid]
        if per_page.get(page, 0) >= PER_PAGE:
            continue
        per_page[page] = per_page.get(page, 0) + 1
        picked.append(cid)
        if len(picked) == TOP_K:
            break
    return [
        Source(
            n=first_n + k,
            document_id=None,
            filename=results[owner[cid]].title,
            page=None,
            text=candidates[cid].text,
            url=pages[owner[cid]][0],
        )
        for k, cid in enumerate(picked)
    ]


def results_text(results: list[SearchResult]) -> str:
    """Search results as the web_search tool reports them to the model."""
    if not results:
        return "No results."
    return "\n\n".join(
        f"{i}. {r.title}\n{r.url}\n{r.snippet}" for i, r in enumerate(results, start=1)
    )

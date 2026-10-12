"""Search engines, turning result pages into sources, and web search in chat."""

import json

import httpx
import pytest
import respx

import app.routers.chat as chat_module
import app.tools.web as web
import app.websearch.engines as engines
from app.rag.service import build_context
from app.routers.chat import stream_and_persist
from app.schemas import ChatMessage, ChatParams, StreamChunk
from app.tools.registry import ToolContext, run_tool
from app.websearch.engines import (
    SearchError,
    SearchResult,
    WebSearchConfig,
    search,
)
from app.websearch.service import make_search_query, web_sources
from tests.test_tool_calling import ScriptedProvider, events

PAGE_A = "<html><body><h1>Python 3.14</h1><p>Python 3.14 was released on 7 October 2025.</p>"
PAGE_B = "<html><body><p>Unrelated cooking recipes and pasta.</p></body></html>"


@pytest.fixture
def dns(monkeypatch):
    async def resolve(host, port):
        if host == "internal.test":
            return ["10.0.0.1"]
        return ["93.184.216.34"]

    monkeypatch.setattr(web, "resolve_host", resolve)


@pytest.fixture
def conv(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


# --- engines ----------------------------------------------------------------------


def test_config_enabled_needs_url_or_key() -> None:
    assert not WebSearchConfig("").enabled
    assert WebSearchConfig("duckduckgo").enabled
    assert not WebSearchConfig("searxng").enabled
    assert WebSearchConfig("searxng", base_url="http://s").enabled
    assert not WebSearchConfig("brave").enabled
    assert WebSearchConfig("tavily", api_key="k").enabled


@respx.mock
async def test_searxng(http) -> None:
    route = respx.get("http://searx.test/search").respond(
        json={
            "results": [
                {"title": "A &amp; B", "url": "https://a.test/", "content": "<b>hi</b>"},
                {"title": "dup", "url": "https://a.test/", "content": ""},
                {"title": "bad", "url": "javascript:alert(1)", "content": ""},
                {"title": "", "url": "https://c.test/", "content": "c"},
            ]
        }
    )
    results = await search(http, WebSearchConfig("searxng", base_url="http://searx.test"), "q")
    assert route.calls.last.request.url.params["format"] == "json"
    assert results == [
        SearchResult("A & B", "https://a.test/", "hi"),
        SearchResult("https://c.test/", "https://c.test/", "c"),
    ]


@respx.mock
async def test_brave_and_tavily(http) -> None:
    brave = respx.get("https://api.search.brave.com/res/v1/web/search").respond(
        json={"web": {"results": [{"title": "B", "url": "https://b.test", "description": "d"}]}}
    )
    tavily = respx.post("https://api.tavily.com/search").respond(
        json={"results": [{"title": "T", "url": "https://t.test", "content": "c"}]}
    )
    assert (await search(http, WebSearchConfig("brave", api_key="bk"), "q"))[0].url == (
        "https://b.test"
    )
    assert brave.calls.last.request.headers["X-Subscription-Token"] == "bk"
    assert (await search(http, WebSearchConfig("tavily", api_key="tk"), "q"))[0].title == "T"
    assert tavily.calls.last.request.headers["Authorization"] == "Bearer tk"


@respx.mock
async def test_engine_errors_are_search_errors(http) -> None:
    respx.post("https://api.tavily.com/search").respond(401)
    with pytest.raises(SearchError, match="rejected the API key"):
        await search(http, WebSearchConfig("tavily", api_key="bad"), "q")
    respx.get("http://searx.test/search").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(SearchError, match="Couldn't reach"):
        await search(http, WebSearchConfig("searxng", base_url="http://searx.test"), "q")


async def test_duckduckgo_uses_ddgs(http, monkeypatch) -> None:
    calls = []

    def fake(query, count):
        calls.append((query, count))
        return [SearchResult("D", "https://d.test", "s")]

    monkeypatch.setattr(engines, "_ddgs", fake)
    results = await search(http, WebSearchConfig("duckduckgo", result_count=2), "  hello  ")
    assert results == [SearchResult("D", "https://d.test", "s")]
    assert calls == [("hello", 4)]  # asks for a few spare results


# --- results -> sources -------------------------------------------------------------


@respx.mock
async def test_web_sources_ranks_passages_and_falls_back_to_snippets(http, dns) -> None:
    respx.get("https://a.test/").respond(html=PAGE_A)
    respx.get("https://b.test/").respond(html=PAGE_B)
    results = [
        SearchResult("Pasta", "https://b.test/", "recipes"),
        SearchResult("Python news", "https://a.test/", "release"),
        SearchResult("Internal", "http://internal.test/", "the snippet"),
    ]
    sources = await web_sources(http, results, "When was Python 3.14 released?", first_n=3)
    # The matching page comes first; the others still contribute their opening text.
    assert [(s.n, s.filename, s.url) for s in sources] == [
        (3, "Python news", "https://a.test/"),
        (4, "Pasta", "https://b.test/"),
        (5, "Internal", "http://internal.test/"),
    ]
    assert "7 October 2025" in sources[0].text
    # An internal address is never fetched: its search snippet is used instead.
    assert sources[2].text == "the snippet"
    context = build_context(sources)
    assert "[3] (Python news, https://a.test/)" in context
    assert "not instructions" in context


async def test_first_message_is_searched_as_written() -> None:
    provider = ScriptedProvider([])
    history = [ChatMessage(role="system", content="x"), ChatMessage(role="user", content="hi?")]
    assert await make_search_query(provider, "m", history) == "hi?"
    assert provider.seen == []


async def test_follow_up_is_rewritten_by_the_model() -> None:
    provider = ScriptedProvider(
        [[StreamChunk(delta='"Python 3.15 release date"\nextra'), StreamChunk(done=True)]]
    )
    history = [
        ChatMessage(role="user", content="When was Python 3.14 released?"),
        ChatMessage(role="assistant", content="October 2025."),
        ChatMessage(role="user", content="And the next one?"),
    ]
    assert await make_search_query(provider, "m", history) == "Python 3.15 release date"
    sent = provider.seen[0][0]
    assert sent[0].role == "system" and "And the next one?" in sent[1].content


# --- the web_search tool ----------------------------------------------------------


async def test_web_search_tool(http, monkeypatch) -> None:
    async def fake_search(http, config, query, count=None):
        return [SearchResult("T", "https://t.test", "snippet")]

    monkeypatch.setattr("app.tools.registry.search", fake_search)
    off = await run_tool("web_search", {"query": "x"}, ToolContext(http=http))
    assert off.error and "isn't set up" in off.output
    ctx = ToolContext(http=http, web_search=WebSearchConfig("duckduckgo"))
    out = await run_tool("web_search", {"query": "x"}, ctx)
    assert not out.error and out.output == "1. T\nhttps://t.test\nsnippet"


# --- chat ---------------------------------------------------------------------------


async def test_chat_searches_first_and_cites_pages(app, client, conv, http, monkeypatch) -> None:
    async def fake_search(http, config, query, count=None):
        assert query == "When was Python 3.14 released?"
        return [SearchResult("Python news", "https://a.test/", "s")]

    monkeypatch.setattr(chat_module, "search", fake_search)
    with respx.mock:
        respx.get("https://a.test/").respond(html=PAGE_A)
        monkeypatch.setattr(web, "resolve_host", lambda h, p: _public())
        provider = ScriptedProvider([[StreamChunk(delta="Oct 2025 [1]"), StreamChunk(done=True)]])
        history = [
            ChatMessage(role="system", content="Be brief."),
            ChatMessage(role="user", content="When was Python 3.14 released?"),
        ]
        out = [
            e
            async for e in stream_and_persist(
                app.state.engine,
                provider,
                conv,
                "ollama:m",
                "m",
                history,
                ChatParams(),
                web_search=WebSearchConfig("duckduckgo"),
                http=http,
            )
        ]
    evts = events(out)
    assert evts[0] == {
        "tool_call": {
            "id": "web_search",
            "name": "web_search",
            "arguments": {"query": "When was Python 3.14 released?"},
        }
    }
    assert evts[1]["tool_result"]["output"] == "Read 1 page\nhttps://a.test/"
    assert evts[2]["sources"][0]["url"] == "https://a.test/"
    sent = provider.seen[0][0]
    # The custom instructions stay first; the web excerpts follow them.
    assert sent[0].content == "Be brief." and "<sources>" in sent[1].content
    saved = client.get(f"/api/conversations/{conv}").json()["messages"][-1]
    assert saved["sources"][0]["url"] == "https://a.test/"
    assert saved["sources"][0]["document_id"] is None
    assert saved["tools"][0]["name"] == "web_search"


async def test_failed_search_is_reported_and_answered_anyway(app, client, conv, http, monkeypatch):
    async def broken(http, config, query, count=None):
        raise SearchError("rate limit reached")

    monkeypatch.setattr(chat_module, "search", broken)
    provider = ScriptedProvider([[StreamChunk(delta="From memory…"), StreamChunk(done=True)]])
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine,
            provider,
            conv,
            "ollama:m",
            "m",
            [ChatMessage(role="user", content="news?")],
            ChatParams(),
            web_search=WebSearchConfig("duckduckgo"),
            http=http,
        )
    ]
    evts = events(out)
    assert evts[1]["tool_result"] == {
        "id": "web_search",
        "output": "rate limit reached",
        "error": True,
    }
    assert "rate limit reached" in provider.seen[0][0][0].content
    assert evts[-1]["done"] is True


async def _public():
    return ["93.184.216.34"]


# --- admin & endpoint ---------------------------------------------------------------


def test_admin_web_search_settings(client, user_client) -> None:
    assert client.get("/api/config").json()["web_search"] is False
    assert "web_search" not in [t["id"] for t in user_client.get("/api/tools").json()]
    assert client.put("/api/admin/web-search", json={"engine": "brave"}).status_code == 422
    assert client.put("/api/admin/web-search", json={"engine": "searxng"}).status_code == 422
    saved = client.put(
        "/api/admin/web-search",
        json={"engine": "tavily", "api_key": "secret", "result_count": 4},
    ).json()
    assert saved == {"engine": "tavily", "base_url": "", "result_count": 4, "has_key": True}
    # Keeping the key when it's omitted.
    assert client.put("/api/admin/web-search", json={"engine": "tavily", "result_count": 5}).json()[
        "has_key"
    ]
    assert user_client.get("/api/admin/web-search").status_code == 403
    assert client.get("/api/config").json()["web_search"] is True
    assert "web_search" in [t["id"] for t in user_client.get("/api/tools").json()]


@respx.mock
def test_admin_test_search(client) -> None:
    client.put("/api/admin/web-search", json={"engine": "searxng", "base_url": "http://s.test/"})
    respx.get("http://s.test/search").respond(
        json={"results": [{"title": "R", "url": "https://r.test", "content": "c"}]}
    )
    data = client.post("/api/admin/web-search/test", json={"query": "hello"}).json()
    assert data == {
        "ok": True,
        "results": [{"title": "R", "url": "https://r.test", "snippet": "c"}],
    }


def test_chat_refuses_web_search_when_off(client, conv) -> None:
    resp = client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:m", "message": "hi", "web_search": True},
    )
    assert resp.status_code in (400, 404)  # no provider either way; never streams


@respx.mock
def test_chat_endpoint_passes_web_search(client, session, conv, monkeypatch) -> None:
    from app.models import Provider

    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url="http://o.test"))
    session.commit()
    client.put("/api/admin/web-search", json={"engine": "duckduckgo"})

    async def fake_search(http, config, query, count=None):
        return []

    monkeypatch.setattr(chat_module, "search", fake_search)
    route = respx.post("http://o.test/api/chat").respond(
        content=json.dumps({"message": {"content": "ok"}, "done": True}).encode() + b"\n"
    )
    resp = client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:m", "message": "hi", "web_search": True},
    )
    assert '"name": "web_search"' in resp.text and '"output": "No results."' in resp.text
    sent = json.loads(route.calls.last.request.content)["messages"]
    assert "found nothing usable" in sent[0]["content"]


def test_ddgs_retries_when_its_backends_come_back_empty(monkeypatch) -> None:
    import ddgs
    from ddgs.exceptions import DDGSException

    replies = [DDGSException("No results found."), [{"title": "T", "href": "https://t.test"}]]

    class FakeDDGS:
        def __init__(self, timeout):
            pass

        def text(self, query, max_results):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

    monkeypatch.setattr(ddgs, "DDGS", FakeDDGS)
    monkeypatch.setattr(engines, "DDGS_RETRY_PAUSE", 0)
    assert engines._ddgs("q", 3) == [SearchResult("T", "https://t.test", "")]
    replies[:] = [DDGSException("No results found.")] * 3
    assert engines._ddgs("q", 3) == []
    replies[:] = [DDGSException("ratelimit")]
    with pytest.raises(SearchError, match="ratelimit"):
        engines._ddgs("q", 3)

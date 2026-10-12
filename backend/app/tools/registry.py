"""Built-in tools the model can call, with JSON-Schema parameters."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.tools.calculator import CalculatorError, calculate
from app.tools.web import FetchError, fetch_text
from app.websearch.engines import SearchError, WebSearchConfig, search
from app.websearch.service import results_text

MAX_OUTPUT_CHARS = 8_000


class ToolInputError(ValueError):
    """Bad arguments from the model; reported back to it as the tool's error."""


@dataclass(frozen=True)
class ToolContext:
    http: httpx.AsyncClient
    web_search: WebSearchConfig | None = None


@dataclass(frozen=True)
class Tool:
    id: str
    label: str
    emoji: str
    description: str  # what the model sees
    summary: str  # what users see
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any], ToolContext], Awaitable[str]]


def _string_arg(
    args: dict[str, Any], name: str, required: bool = True, max_len: int = 2000
) -> str | None:
    value = args.get(name)
    if value is None or value == "":
        if required:
            raise ToolInputError(f"Missing '{name}'")
        return None
    if not isinstance(value, str) or len(value) > max_len:
        raise ToolInputError(f"'{name}' must be a string of at most {max_len} characters")
    return value


async def _calculator(args: dict[str, Any], ctx: ToolContext) -> str:
    expression = _string_arg(args, "expression", max_len=500)
    try:
        return calculate(expression or "")
    except CalculatorError as exc:
        raise ToolInputError(str(exc)) from exc


async def _current_time(args: dict[str, Any], ctx: ToolContext) -> str:
    name = _string_arg(args, "timezone", required=False, max_len=64) or "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ToolInputError(
            f"Unknown timezone '{name}'. Use an IANA name like 'Asia/Kolkata'."
        ) from exc
    now = datetime.now(zone)
    offset = now.strftime("%z")
    return f"{now.strftime('%A, %d %B %Y, %H:%M:%S')} ({name}, UTC{offset[:3]}:{offset[3:]})"


async def _fetch_url(args: dict[str, Any], ctx: ToolContext) -> str:
    url = _string_arg(args, "url", max_len=2000) or ""
    try:
        final_url, text = await fetch_text(ctx.http, url.strip())
    except FetchError as exc:
        raise ToolInputError(str(exc)) from exc
    return f"Content of {final_url}:\n\n{text or '(the page has no readable text)'}"


async def _web_search(args: dict[str, Any], ctx: ToolContext) -> str:
    query = _string_arg(args, "query", max_len=400) or ""
    if ctx.web_search is None or not ctx.web_search.enabled:
        raise ToolInputError("Web search isn't set up on this server")
    try:
        results = await search(ctx.http, ctx.web_search, query, count=5)
    except SearchError as exc:
        raise ToolInputError(str(exc)) from exc
    return results_text(results)


TOOLS: dict[str, Tool] = {
    t.id: t
    for t in (
        Tool(
            id="calculator",
            label="Calculator",
            emoji="🧮",
            description=(
                "Evaluate a math expression exactly. Use it for any arithmetic instead of "
                "computing in your head. Supports + - * / // % ** (or ^), parentheses, pi, e, "
                "and sqrt, abs, round, floor, ceil, exp, log (natural; log(x, base)), log10, "
                "log2, sin, cos, tan, "
                "asin, acos, atan, radians, degrees, factorial, min, max."
            ),
            summary="Exact arithmetic and math functions",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "e.g. 23*47 or sqrt(2)*pi"}
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
            run=_calculator,
        ),
        Tool(
            id="current_time",
            label="Current time",
            emoji="🕐",
            description=(
                "Get the current date and time, optionally in a given IANA timezone (default UTC)."
            ),
            summary="Today's date and time in any timezone",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "e.g. America/Phoenix, Asia/Kolkata",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
            run=_current_time,
        ),
        Tool(
            id="fetch_url",
            label="Fetch web page",
            emoji="🌐",
            description=(
                "Download a public web page and return its readable text (up to ~8000 characters). "
                "Use when the user gives a URL or asks about a specific page's content."
            ),
            summary="Read the text of a public web page",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Full http(s) URL"}},
                "required": ["url"],
                "additionalProperties": False,
            },
            run=_fetch_url,
        ),
        Tool(
            id="web_search",
            label="Web search",
            emoji="🔎",
            description=(
                "Search the web. Returns the top results with title, URL and a snippet. Use it "
                "for recent events or facts you aren't sure of; read a result in full with "
                "fetch_url if it's available. Cite the URLs you use."
            ),
            summary="Search the internet for current information",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search terms"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            run=_web_search,
        ),
    )
}


@dataclass(frozen=True)
class ToolOutcome:
    output: str
    error: bool


async def run_tool(tool_id: str, args: Any, ctx: ToolContext) -> ToolOutcome:
    tool = TOOLS.get(tool_id)
    if tool is None:
        return ToolOutcome(f"Unknown tool '{tool_id}'", True)
    if not isinstance(args, dict):
        return ToolOutcome("Arguments must be a JSON object", True)
    try:
        output = await tool.run(args, ctx)
    except ToolInputError as exc:
        return ToolOutcome(str(exc), True)
    if len(output) > MAX_OUTPUT_CHARS:
        # Say so, so the model knows it didn't see everything.
        output = output[: MAX_OUTPUT_CHARS - 15] + "\n…(truncated)"
    return ToolOutcome(output, False)

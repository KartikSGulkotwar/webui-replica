import httpx
import pytest
import respx

import app.tools.web as web
from app.tools.calculator import CalculatorError, calculate
from app.tools.registry import ToolContext, run_tool


@pytest.fixture
def dns(monkeypatch):
    """Stub DNS: hostnames map to the given IPs."""
    table = {
        "example.test": ["93.184.216.34"],
        "internal.test": ["10.1.2.3"],
        "mapped.test": ["::ffff:127.0.0.1"],
        "metadata.test": ["169.254.169.254"],
    }

    async def resolve(host, port):
        if host not in table:
            raise OSError("not found")
        return table[host]

    monkeypatch.setattr(web, "resolve_host", resolve)
    return table


@pytest.fixture
def ctx(http) -> ToolContext:
    return ToolContext(http=http)


# --- calculator -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "result"),
    [
        ("23*47", "1081"),
        ("2^10", "1024"),
        ("(1+2)*3", "9"),
        ("10/4", "2.5"),
        ("7//2", "3"),
        ("-3**2", "-9"),
        ("sqrt(16)", "4"),
        ("round(pi, 3)", "3.142"),
        ("log(1000, 10)", "3"),
        ("factorial(10)", "3628800"),
        ("max(3, 9, 4)", "9"),
        ("12 × 3 ÷ 4", "9"),
        ("0.1+0.2", "0.3"),
        ("log(8, 2)", "3"),
        ("sin(pi)", "0"),
    ],
)
def test_calculator(expression, result) -> None:
    assert calculate(expression) == result


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('ls')",
        "().__class__.__bases__",
        "open('/etc/passwd')",
        "x + 1",
        "9**9**9",
        "2**100000",
        "factorial(100000)",
        "1/0",
        "sqrt(-1)",
        "'a' * 10",
        "lambda: 1",
        "",
        "1+" * 300,
    ],
)
def test_calculator_rejects(expression) -> None:
    with pytest.raises(CalculatorError):
        calculate(expression)


# --- registry ---------------------------------------------------------------------


async def test_run_tool_reports_errors_to_the_model(ctx) -> None:
    ok = await run_tool("calculator", {"expression": "6*7"}, ctx)
    assert (ok.output, ok.error) == ("42", False)
    for tool, args, message in [
        ("calculator", {}, "Missing 'expression'"),
        ("calculator", {"expression": 5}, "must be a string"),
        ("calculator", "not an object", "JSON object"),
        ("nope", {}, "Unknown tool"),
        ("current_time", {"timezone": "Mars/Base"}, "Unknown timezone"),
    ]:
        outcome = await run_tool(tool, args, ctx)
        assert outcome.error and message in outcome.output


async def test_current_time(ctx) -> None:
    out = await run_tool("current_time", {"timezone": "Asia/Kolkata"}, ctx)
    assert "Asia/Kolkata, UTC+05:30" in out.output
    assert "(UTC, UTC+00:00)" in (await run_tool("current_time", {}, ctx)).output


# --- fetch_url --------------------------------------------------------------------


@respx.mock
async def test_fetch_html_page(dns, ctx) -> None:
    respx.get("https://example.test/article").respond(
        html="<html><head><style>x{}</style><script>evil()</script></head>"
        "<body><h1>Solar drones</h1><p>Acme ships in March.</p></body></html>"
    )
    out = await run_tool("fetch_url", {"url": "https://example.test/article"}, ctx)
    assert not out.error
    assert (
        out.output
        == "Content of https://example.test/article:\n\nSolar drones\nAcme ships in March."
    )


@respx.mock
async def test_fetch_truncates_long_pages(dns, ctx) -> None:
    respx.get("https://example.test/big").respond(
        text="word " * 5000, headers={"content-type": "text/plain"}
    )
    out = await run_tool("fetch_url", {"url": "https://example.test/big"}, ctx)
    assert out.output.endswith("…(truncated)") and len(out.output) < 8200


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.test/file", "Only http"),
        ("file:///etc/passwd", "Only http"),
        ("http://internal.test/admin", "private or internal"),
        ("http://metadata.test/latest/meta-data/", "private or internal"),
        ("http://mapped.test/", "private or internal"),
        ("http://user:pass@example.test/", "credentials"),
        ("http://nowhere.test/", "Couldn't find"),
        ("https:///no-host", "no host"),
    ],
)
async def test_fetch_blocks_unsafe_urls(dns, ctx, url, message) -> None:
    out = await run_tool("fetch_url", {"url": url}, ctx)
    assert out.error and message in out.output


@respx.mock
async def test_redirect_to_internal_address_is_blocked(dns, ctx) -> None:
    respx.get("https://example.test/go").respond(
        302, headers={"location": "http://metadata.test/secrets"}
    )
    internal = respx.get("http://metadata.test/secrets").respond(text="AWS_SECRET")
    out = await run_tool("fetch_url", {"url": "https://example.test/go"}, ctx)
    assert out.error and "private or internal" in out.output
    assert not internal.called  # never requested


@respx.mock
async def test_redirects_are_followed_when_safe(dns, ctx) -> None:
    respx.get("https://example.test/old").respond(301, headers={"location": "/new"})
    respx.get("https://example.test/new").respond(
        text="moved here", headers={"content-type": "text/plain"}
    )
    out = await run_tool("fetch_url", {"url": "https://example.test/old"}, ctx)
    assert out.output == "Content of https://example.test/new:\n\nmoved here"


@respx.mock
async def test_fetch_errors(dns, ctx) -> None:
    respx.get("https://example.test/404").respond(404)
    respx.get("https://example.test/img").respond(
        content=b"\x89PNG", headers={"content-type": "image/png"}
    )
    respx.get("https://example.test/slow").mock(side_effect=httpx.ReadTimeout("slow"))
    assert (
        "HTTP 404" in (await run_tool("fetch_url", {"url": "https://example.test/404"}, ctx)).output
    )
    assert (
        "image/png"
        in (await run_tool("fetch_url", {"url": "https://example.test/img"}, ctx)).output
    )
    assert (
        "too long"
        in (await run_tool("fetch_url", {"url": "https://example.test/slow"}, ctx)).output
    )

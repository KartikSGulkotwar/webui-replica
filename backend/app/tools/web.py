"""Fetch a public web page as text, refusing internal addresses (SSRF guard)."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from app.rag.extract import _TextOnly

MAX_BYTES = 1_000_000
# Leaves room within the tool output limit for the "Content of <url>" header.
MAX_CHARS = 7_500
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "WebUI-Replica/1.0 (+https://github.com/KartikSGulkotwar/webui-replica)"


class FetchError(ValueError):
    pass


async def resolve_host(host: str, port: int) -> list[str]:
    """All IP addresses a host resolves to (separate so tests can stub DNS)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def check_url(url: str) -> None:
    """Only public http(s) addresses: no localhost, private networks, link-local
    (cloud metadata at 169.254.169.254), or other internal ranges."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http:// and https:// URLs can be fetched")
    if not parts.hostname:
        raise FetchError("That URL has no host")
    if parts.username or parts.password:
        raise FetchError("URLs with credentials aren't allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = await resolve_host(parts.hostname, port)
    except OSError as exc:
        raise FetchError(f"Couldn't find {parts.hostname}") from exc
    if not addresses:
        raise FetchError(f"Couldn't find {parts.hostname}")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        # "::ffff:127.0.0.1" is IPv4 loopback in IPv6 clothing: check the IPv4 part.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            raise FetchError("That address is private or internal, so it can't be fetched")


async def fetch_text(
    http: httpx.AsyncClient,
    url: str,
    max_chars: int = MAX_CHARS,
    timeout: httpx.Timeout = TIMEOUT,
) -> tuple[str, str]:
    """Return (final URL, readable text), following redirects one checked hop at a time."""
    for _ in range(MAX_REDIRECTS + 1):
        await check_url(url)
        try:
            async with http.stream(
                "GET",
                url,
                follow_redirects=False,
                timeout=timeout,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5",
                },
            ) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchError("Redirect without a location")
                    url = urljoin(url, location)
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"The page returned HTTP {resp.status_code}")
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type and not (
                    content_type.startswith("text/")
                    or content_type in ("application/json", "application/xhtml+xml")
                ):
                    raise FetchError(f"Can't read {content_type} content")
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        body = body[:MAX_BYTES]
                        break
                text = body.decode(resp.encoding or "utf-8", errors="replace")
        except httpx.TimeoutException as exc:
            raise FetchError("The page took too long to respond") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Couldn't fetch the page: {exc.__class__.__name__}") from exc
        if "html" in content_type or text.lstrip().lower().startswith(("<!doctype html", "<html")):
            parser = _TextOnly()
            parser.feed(text)
            text = "".join(parser.parts)
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…(truncated)"
        return url, text
    raise FetchError("Too many redirects")

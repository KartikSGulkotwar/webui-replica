import math
import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request


def client_ip(request: Request, trusted_proxy_hops: int) -> str:
    """The caller's IP, honouring X-Forwarded-For only from trusted proxies.

    Each trusted proxy appends the address it saw, so the real client is the
    entry `hops` from the right. Entries further left are client-supplied and
    could be forged, so they are never used.
    """
    if trusted_proxy_hops > 0:
        forwarded = [
            h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()
        ]
        if len(forwarded) >= trusted_proxy_hops:
            return forwarded[-trusted_proxy_hops]
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """In-memory sliding-window limiter: at most `limit` hits per `window` seconds
    per key. Per process, which suits a single-instance demo."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._last_sweep = clock()

    def hit(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until a slot frees up."""
        now = self._clock()
        with self._lock:
            self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - now
            hits.append(now)
            return None

    def _sweep(self, now: float) -> None:
        # Drop idle keys now and then so memory doesn't grow with every visitor.
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]


def limit_chat(request: Request) -> None:
    limiter: RateLimiter | None = request.app.state.chat_limiter
    if limiter is None:
        return
    key = client_ip(request, request.app.state.settings.trusted_proxy_hops)
    retry_after = limiter.hit(key)
    if retry_after is not None:
        seconds = max(1, math.ceil(retry_after))
        raise HTTPException(
            status_code=429,
            detail=f"Too many messages. Please wait {seconds} seconds and try again.",
            headers={"Retry-After": str(seconds)},
        )

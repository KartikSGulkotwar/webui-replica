import math
import random
import time
from collections.abc import Callable

from fastapi import HTTPException, Request
from sqlalchemy import Engine, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import RateLimitBucket

INSERTS = {"postgresql": pg_insert, "sqlite": sqlite_insert}


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
    """At most `limit` hits per key in each fixed `window`, counted in the database
    with an atomic upsert, so every process and serverless instance shares it."""

    def __init__(
        self,
        engine: Engine,
        limit: int,
        window: int = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        insert = INSERTS.get(engine.dialect.name)
        if insert is None:
            raise ValueError(f"Rate limiting needs SQLite or Postgres, not {engine.dialect.name}")
        self._insert = insert
        self.engine = engine
        self.limit = limit
        self.window = window
        self._clock = clock

    def hit(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the window resets."""
        now = self._clock()
        start = int(now // self.window * self.window)
        table = RateLimitBucket.__table__
        stmt = (
            self._insert(table)
            .values(key=key[:100], window_start=start, count=1)
            .on_conflict_do_update(
                index_elements=["key", "window_start"], set_={"count": table.c.count + 1}
            )
            .returning(table.c.count)
        )
        with self.engine.begin() as conn:
            count = conn.execute(stmt).scalar_one()
            # Occasionally drop finished windows so the table stays small.
            if random.random() < 0.05:
                conn.execute(delete(table).where(table.c.window_start < start))
        if count > self.limit:
            return start + self.window - now
        return None


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

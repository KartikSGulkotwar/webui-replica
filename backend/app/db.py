import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        # An in-memory DB lives only as long as its connection, so share one.
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(database_url, **kwargs)
    return create_engine(database_url, pool_pre_ping=True)


def run_migrations(database_url: str, revision: str = "head") -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, revision)


def wait_for_database(engine: Engine, timeout: float = 60.0, interval: float = 2.0) -> None:
    """Retry until the database answers (in Kubernetes it often starts after
    the app), instead of crashing and being restarted."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            if time.monotonic() >= deadline:
                raise
            logger.warning("Waiting for the database: %s", str(exc).splitlines()[0])
            time.sleep(interval)


# Arbitrary constant: the Postgres advisory lock that serializes startup work.
STARTUP_LOCK_KEY = 72_061_917


@contextmanager
def startup_lock(engine: Engine) -> Iterator[None]:
    """Postgres: one replica at a time runs migrations and seeding (Kubernetes
    starts several at once); the others wait, then find the work done. SQLite
    runs as a single process, so there's nothing to coordinate."""
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": STARTUP_LOCK_KEY})
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": STARTUP_LOCK_KEY})


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

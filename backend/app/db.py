from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        # An in-memory DB lives only as long as its connection, so share one.
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(database_url, **kwargs)
    return create_engine(database_url, pool_pre_ping=True)


def run_migrations(database_url: str) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

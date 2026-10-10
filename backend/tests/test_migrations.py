import os

import pytest
from sqlalchemy import inspect, text

from app.db import make_engine, run_migrations

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")


def check_migrations(url: str) -> None:
    run_migrations(url)
    run_migrations(url)  # idempotent at head
    engine = make_engine(url)
    try:
        assert {"providers", "conversations", "messages"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_sqlite(tmp_path) -> None:
    check_migrations(f"sqlite:///{tmp_path / 'm.db'}")


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_POSTGRES_URL to run against Postgres")
def test_migrations_postgres() -> None:
    engine = make_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()
    check_migrations(POSTGRES_URL)

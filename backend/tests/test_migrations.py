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


def upgrade_with_existing_rows(url: str) -> None:
    """New NOT NULL columns must get values for rows that already exist."""
    run_migrations(url, "0005")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into conversations (id, title, owner_id, created_at, updated_at) "
                "values ('c1', 'Old chat', null, current_timestamp, current_timestamp)"
            )
        )
        conn.execute(
            text(
                "insert into messages (conversation_id, role, content, created_at) "
                "values ('c1', 'user', 'hi', current_timestamp)"
            )
        )
    run_migrations(url)
    with engine.connect() as conn:
        row = conn.execute(text("select pinned, archived, system_prompt from conversations")).one()
        assert (bool(row.pinned), bool(row.archived), row.system_prompt) == (False, False, None)
        assert conn.execute(text("select rating from messages")).scalar() is None
    engine.dispose()


def test_upgrade_keeps_existing_data_sqlite(tmp_path) -> None:
    upgrade_with_existing_rows(f"sqlite:///{tmp_path / 'u.db'}")


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_POSTGRES_URL to run against Postgres")
def test_upgrade_keeps_existing_data_postgres() -> None:
    engine = make_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()
    upgrade_with_existing_rows(POSTGRES_URL)

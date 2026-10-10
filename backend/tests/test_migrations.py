from sqlalchemy import inspect

from app.db import make_engine, run_migrations


def test_migrations_create_tables(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    run_migrations(url)  # idempotent at head
    engine = make_engine(url)
    assert {"providers", "conversations", "messages"} <= set(inspect(engine).get_table_names())
    engine.dispose()

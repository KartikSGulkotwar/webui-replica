from logging.config import fileConfig

from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers tables on SQLModel.metadata)
from alembic import context
from app.config import get_settings
from app.db import make_engine

config = context.config

# When run from the CLI, configure logging from alembic.ini. When the app runs
# migrations on startup it sets sqlalchemy.url and keeps its own logging.
if config.config_file_name is not None and not config.get_main_option("sqlalchemy.url"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

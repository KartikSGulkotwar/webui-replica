"""An embedding column: pgvector on Postgres, JSON text elsewhere (SQLite)."""

import json

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator, UserDefinedType


class _PgVector(UserDefinedType):
    """pgvector's `vector` type, without a fixed dimension, so any embedding
    model works (rows are always filtered by model before comparing)."""

    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "vector"


class Embedding(TypeDecorator):
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVector())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        # pgvector accepts the same "[1.0,2.0]" text form JSON produces.
        return json.dumps([float(x) for x in value], separators=(",", ":"))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in json.loads(value)] if isinstance(value, str) else list(value)

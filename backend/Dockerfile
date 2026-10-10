FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Used only when DATABASE_URL isn't provided.
    DATABASE_URL=sqlite:////app/data/webui.db

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install .
COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --uid 10001 app && mkdir -p /app/data && chown app /app/data
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

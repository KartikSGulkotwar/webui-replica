import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import __version__
from app.config import Settings, get_settings
from app.crypto import KeyCipher
from app.db import make_engine, run_migrations
from app.providers.registry import ProviderRegistry
from app.routers import health, models
from app.seed import seed_providers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    if settings.auto_migrate:
        run_migrations(settings.database_url)
    with Session(app.state.engine) as session:
        seed_providers(session, settings, app.state.cipher)

    client = httpx.AsyncClient(follow_redirects=True)
    app.state.registry = ProviderRegistry(client, app.state.cipher)
    try:
        yield
    finally:
        await client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.cipher = KeyCipher(settings.encryption_key)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(models.router)
    return app


app = create_app()

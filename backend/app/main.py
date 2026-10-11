import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import __version__
from app.config import Settings, get_settings
from app.crypto import KeyCipher
from app.db import BACKEND_DIR, make_engine, run_migrations
from app.providers.registry import ProviderRegistry
from app.ratelimit import RateLimiter
from app.routers import chat, conversations, health, models, providers
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
    app.state.http = client
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
    app.state.chat_limiter = (
        RateLimiter(app.state.engine, settings.chat_rate_limit_per_minute)
        if settings.chat_rate_limit_per_minute > 0
        else None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(providers.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)

    # On Vercel the build step puts the compiled frontend here and the app serves
    # it (Vercel moves it to its CDN). Docker and local dev use nginx/Vite instead.
    static_dir = BACKEND_DIR / "static"
    if (static_dir / "index.html").is_file():
        app.frontend("/", directory=static_dir)
    return app


app = create_app()

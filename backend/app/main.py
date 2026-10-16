import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import __version__
from app.config import Settings, get_settings
from app.crypto import KeyCipher
from app.db import BACKEND_DIR, make_engine, run_migrations, startup_lock, wait_for_database
from app.observability import (
    BUILD_INFO,
    ObservabilityMiddleware,
    configure_logging,
    setup_tracing,
)
from app.providers.registry import ProviderRegistry
from app.ratelimit import RateLimiter
from app.routers import (
    admin,
    audio,
    auth,
    channels,
    chat,
    conversations,
    custom_models,
    health,
    images,
    knowledge,
    memories,
    models,
    notes,
    providers,
    shared,
)
from app.seed import seed_admin, seed_providers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    wait_for_database(app.state.engine, settings.database_wait_seconds)
    with startup_lock(app.state.engine):
        if settings.auto_migrate:
            run_migrations(settings.database_url)
        with Session(app.state.engine) as session:
            seed_providers(session, settings, app.state.cipher)
            seed_admin(session, settings)

    client = httpx.AsyncClient(follow_redirects=True)
    app.state.http = client
    app.state.registry = ProviderRegistry(client, app.state.cipher)
    try:
        yield
    finally:
        await client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_format, settings.log_level)
    BUILD_INFO.info({"version": __version__})
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.cipher = KeyCipher(settings.encryption_key)
    app.state.chat_limiter = (
        RateLimiter(app.state.engine, settings.chat_rate_limit_per_minute)
        if settings.chat_rate_limit_per_minute > 0
        else None
    )
    app.state.auth_limiter = (
        RateLimiter(app.state.engine, settings.auth_rate_limit_per_minute)
        if settings.auth_rate_limit_per_minute > 0
        else None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # Added last, so it's outermost: it times and logs everything, CORS included.
    app.add_middleware(ObservabilityMiddleware)
    if settings.otel_exporter_otlp_endpoint:
        setup_tracing(app, app.state.engine, settings.otel_service_name, __version__)
        logger.info("OpenTelemetry tracing to %s", settings.otel_exporter_otlp_endpoint)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(models.router)
    app.include_router(providers.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(shared.router)
    app.include_router(knowledge.router)
    app.include_router(custom_models.router)
    app.include_router(memories.router)
    app.include_router(images.router)
    app.include_router(audio.router)
    app.include_router(notes.router)
    app.include_router(channels.router)

    # On Vercel the build step puts the compiled frontend here and the app serves
    # it (Vercel moves it to its CDN). Docker and local dev use nginx/Vite instead.
    static_dir = BACKEND_DIR / "static"
    if (static_dir / "index.html").is_file():
        app.frontend("/", directory=static_dir)
    return app


app = create_app()

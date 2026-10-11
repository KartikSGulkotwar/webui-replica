"""Build step for Vercel (run from backend/ via [tool.vercel.scripts] build).

1. Applies database migrations and seeds providers and the admin account, so cold starts don't race
   to do it (set AUTO_MIGRATE=false in the Vercel project).
2. Builds the React frontend and copies it to backend/static, which the app
   serves with app.frontend() and Vercel promotes to its CDN.
"""

import logging
import os
import shutil
import subprocess
import sys

from sqlmodel import Session

from app.config import get_settings
from app.crypto import KeyCipher
from app.db import BACKEND_DIR, make_engine, run_migrations
from app.seed import seed_admin, seed_providers

FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
STATIC_DIR = BACKEND_DIR / "static"

log = logging.getLogger("vercel_build")


def migrate_and_seed() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        sys.exit("DATABASE_URL must point at Postgres (e.g. Neon) for Vercel deployments")
    log.info("Running migrations")
    run_migrations(settings.database_url)
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        seeded = seed_providers(session, settings, KeyCipher(settings.encryption_key))
        if seed_admin(session, settings):
            log.info("Created admin account %s", settings.admin_email)
    engine.dispose()
    log.info("Seeded providers: %s", ", ".join(seeded) or "none (table not empty)")


def build_frontend() -> None:
    if not FRONTEND_DIR.is_dir():
        sys.exit(
            f"{FRONTEND_DIR} not found. In the Vercel project settings, keep "
            '"Include files outside the root directory in the Build Step" enabled.'
        )
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm is not available in this build environment")
    log.info("Building frontend")
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, check=True)
    # Same-origin API: the frontend calls /api on the domain it was served from.
    env = {**os.environ, "VITE_API_URL": ""}
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True, env=env)
    shutil.rmtree(STATIC_DIR, ignore_errors=True)
    shutil.copytree(FRONTEND_DIR / "dist", STATIC_DIR)
    log.info("Frontend copied to %s", STATIC_DIR)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    migrate_and_seed()
    build_frontend()


if __name__ == "__main__":
    main()

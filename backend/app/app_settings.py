"""Settings admins change at runtime. Env vars provide the initial values."""

import json

from sqlmodel import Session

from app.config import Settings
from app.models import AppSetting
from app.schemas import AdminSettings

KEYS = ("enable_signup", "default_user_role", "enabled_tools", "arena_models")
MAX_ARENA_MODELS = 12


def get_admin_settings(session: Session, settings: Settings) -> AdminSettings:
    values = {
        "enable_signup": settings.enable_signup,
        "default_user_role": settings.default_user_role,
        "enabled_tools": [t.strip() for t in settings.enabled_tools.split(",") if t.strip()],
        "arena_models": [m.strip() for m in settings.arena_models.split(",") if m.strip()],
    }
    for key in KEYS:
        row = session.get(AppSetting, key)
        if row is not None:
            values[key] = json.loads(row.value)
    from app.tools.registry import TOOLS

    values["enabled_tools"] = [t for t in values["enabled_tools"] if t in TOOLS]
    return AdminSettings(**values)


def save_admin_settings(session: Session, new: AdminSettings, settings: Settings) -> AdminSettings:
    from app.tools.registry import TOOLS

    current = get_admin_settings(session, settings)
    if new.enabled_tools is None:
        new = new.model_copy(update={"enabled_tools": current.enabled_tools})
    if new.arena_models is None:
        new = new.model_copy(update={"arena_models": current.arena_models})
    unknown = set(new.enabled_tools or []) - set(TOOLS)
    if unknown:
        raise ValueError(f"Unknown tool: {sorted(unknown)[0]}")
    arena = list(dict.fromkeys(new.arena_models or []))
    if len(arena) > MAX_ARENA_MODELS:
        raise ValueError(f"Choose at most {MAX_ARENA_MODELS} arena models")
    for model_id in arena:
        provider, _, name = model_id.partition(":")
        if not provider or not name or provider in ("persona", "arena"):
            raise ValueError(f"Not a provider model: {model_id}")
    new = new.model_copy(update={"arena_models": arena})
    for key, value in new.model_dump().items():
        row = session.get(AppSetting, key) or AppSetting(key=key, value="null")
        row.value = json.dumps(value)
        session.add(row)
    session.commit()
    return new


def usable_tools(session: Session, settings: Settings, cipher) -> list:
    """Tools people can turn on now: enabled by an admin, and set up (web search
    needs a search engine, images an image engine)."""
    from app.images.service import image_config
    from app.tools.registry import TOOLS
    from app.websearch.service import web_search_config

    enabled = get_admin_settings(session, settings).enabled_tools
    ready = {
        "web_search": web_search_config(session, settings, cipher).enabled,
        "generate_image": image_config(session, settings, cipher).enabled,
    }
    return [t for t in TOOLS.values() if t.id in enabled and ready.get(t.id, True)]

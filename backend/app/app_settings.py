"""Settings admins change at runtime. Env vars provide the initial values."""

import json

from sqlmodel import Session

from app.config import Settings
from app.models import AppSetting
from app.schemas import AdminSettings

KEYS = ("enable_signup", "default_user_role", "enabled_tools")


def get_admin_settings(session: Session, settings: Settings) -> AdminSettings:
    values = {
        "enable_signup": settings.enable_signup,
        "default_user_role": settings.default_user_role,
        "enabled_tools": [t.strip() for t in settings.enabled_tools.split(",") if t.strip()],
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

    if new.enabled_tools is None:
        new = new.model_copy(
            update={"enabled_tools": get_admin_settings(session, settings).enabled_tools}
        )
    unknown = set(new.enabled_tools or []) - set(TOOLS)
    if unknown:
        raise ValueError(f"Unknown tool: {sorted(unknown)[0]}")
    for key, value in new.model_dump().items():
        row = session.get(AppSetting, key) or AppSetting(key=key, value="null")
        row.value = json.dumps(value)
        session.add(row)
    session.commit()
    return new


def usable_tools(session: Session, settings: Settings, cipher) -> list:
    """Tools people can turn on now: enabled by an admin, and web search only
    once a search engine is set up."""
    from app.tools.registry import TOOLS
    from app.websearch.service import web_search_config

    enabled = get_admin_settings(session, settings).enabled_tools
    search_ready = web_search_config(session, settings, cipher).enabled
    return [t for t in TOOLS.values() if t.id in enabled and (t.id != "web_search" or search_ready)]

"""Settings admins change at runtime. Env vars provide the initial values."""

import json

from sqlmodel import Session

from app.config import Settings
from app.models import AppSetting
from app.schemas import AdminSettings

KEYS = ("enable_signup", "default_user_role")


def get_admin_settings(session: Session, settings: Settings) -> AdminSettings:
    values = {
        "enable_signup": settings.enable_signup,
        "default_user_role": settings.default_user_role,
    }
    for key in KEYS:
        row = session.get(AppSetting, key)
        if row is not None:
            values[key] = json.loads(row.value)
    return AdminSettings(**values)


def save_admin_settings(session: Session, new: AdminSettings) -> AdminSettings:
    for key, value in new.model_dump().items():
        row = session.get(AppSetting, key) or AppSetting(key=key, value="null")
        row.value = json.dumps(value)
        session.add(row)
    session.commit()
    return new

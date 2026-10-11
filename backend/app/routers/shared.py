import json

from fastapi import APIRouter, HTTPException

from app.db import SessionDep
from app.models import SharedChat
from app.schemas import SharedChatRead, SharedMessage

router = APIRouter(prefix="/api/shared", tags=["shared"])


@router.get("/{share_id}", response_model=SharedChatRead)
def read_shared(share_id: str, session: SessionDep) -> SharedChatRead:
    """Public: anyone with the link can read the snapshot (no sign-in)."""
    share = session.get(SharedChat, share_id)
    if share is None:
        raise HTTPException(
            status_code=404, detail="This shared chat doesn't exist or was unshared"
        )
    return SharedChatRead(
        title=share.title,
        messages=[SharedMessage(**m) for m in json.loads(share.messages_json)],
        updated_at=share.updated_at,
    )

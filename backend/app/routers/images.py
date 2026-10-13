from fastapi import APIRouter, HTTPException, Response
from sqlmodel import select

from app.auth import OptionalUserDep
from app.db import SessionDep
from app.models import GeneratedImage, SharedChat

router = APIRouter(prefix="/api/images", tags=["images"])


@router.get("/{image_id}")
def read_image(image_id: str, session: SessionDep, user: OptionalUserDep) -> Response:
    """A generated image, for its owner, or for anyone once its chat is shared."""
    image = session.get(GeneratedImage, image_id)
    allowed = image is not None and (
        (user is not None and user.id == image.owner_id)
        or (
            image.conversation_id is not None
            and session.exec(
                select(SharedChat.id).where(SharedChat.conversation_id == image.conversation_id)
            ).first()
            is not None
        )
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=image.data,
        media_type=image.mime,
        # Images never change once made.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )

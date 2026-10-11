from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlmodel import col, delete, select

from app.app_settings import get_admin_settings, save_admin_settings
from app.auth import AdminUserDep
from app.db import SessionDep
from app.models import Conversation, Message, OAuthAccount, SharedChat, User
from app.routers.auth import to_read
from app.schemas import AdminSettings, AdminUserUpdate, UserRead

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_user_or_404(session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(session: SessionDep, admin: AdminUserDep) -> list[UserRead]:
    users = session.exec(select(User).order_by(col(User.created_at))).all()
    return [to_read(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str, body: AdminUserUpdate, session: SessionDep, admin: AdminUserDep
) -> UserRead:
    user = get_user_or_404(session, user_id)
    if user.id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="You can't remove your own admin role")
    user.role = body.role
    session.add(user)
    session.commit()
    session.refresh(user)
    return to_read(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, session: SessionDep, admin: AdminUserDep) -> Response:
    user = get_user_or_404(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account")
    conversation_ids = select(Conversation.id).where(Conversation.owner_id == user.id)
    # Explicit deletes: SQLite doesn't enforce ON DELETE CASCADE by default.
    session.exec(delete(Message).where(col(Message.conversation_id).in_(conversation_ids)))
    session.exec(delete(SharedChat).where(col(SharedChat.conversation_id).in_(conversation_ids)))
    session.exec(delete(Conversation).where(Conversation.owner_id == user.id))
    session.exec(delete(OAuthAccount).where(OAuthAccount.user_id == user.id))
    session.delete(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings", response_model=AdminSettings)
def read_settings(request: Request, session: SessionDep, admin: AdminUserDep) -> AdminSettings:
    return get_admin_settings(session, request.app.state.settings)


@router.put("/settings", response_model=AdminSettings)
def write_settings(body: AdminSettings, session: SessionDep, admin: AdminUserDep) -> AdminSettings:
    return save_admin_settings(session, body)

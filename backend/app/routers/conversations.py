from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import Session, col, delete, select

from app.auth import ActiveUserDep
from app.db import SessionDep
from app.models import DEFAULT_TITLE, Conversation, Message, User, utcnow
from app.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def get_conversation_or_404(session: Session, conversation_id: str, user: User) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    # Someone else's conversation is reported as missing, not forbidden, so IDs
    # can't be probed.
    if conversation is None or conversation.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def list_messages(session: Session, conversation_id: str) -> list[Message]:
    stmt = (
        select(Message).where(Message.conversation_id == conversation_id).order_by(col(Message.id))
    )
    return list(session.exec(stmt).all())


@router.get("", response_model=list[ConversationRead])
def list_conversations(session: SessionDep, user: ActiveUserDep) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.owner_id == user.id)
        .order_by(col(Conversation.updated_at).desc())
    )
    return list(session.exec(stmt).all())


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate, session: SessionDep, user: ActiveUserDep
) -> Conversation:
    conversation = Conversation(title=(body.title or "").strip() or DEFAULT_TITLE, owner_id=user.id)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, session: SessionDep, user: ActiveUserDep
) -> ConversationDetail:
    conversation = get_conversation_or_404(session, conversation_id, user)
    messages = list_messages(session, conversation_id)
    return ConversationDetail(
        **conversation.model_dump(),
        messages=[MessageRead.model_validate(m, from_attributes=True) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationRead)
def rename_conversation(
    conversation_id: str, body: ConversationUpdate, session: SessionDep, user: ActiveUserDep
) -> Conversation:
    conversation = get_conversation_or_404(session, conversation_id, user)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be blank")
    conversation.title = title
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, session: SessionDep, user: ActiveUserDep) -> Response:
    conversation = get_conversation_or_404(session, conversation_id, user)
    # Delete messages explicitly: SQLite doesn't enforce ON DELETE CASCADE by default.
    session.exec(delete(Message).where(col(Message.conversation_id) == conversation_id))
    session.delete(conversation)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

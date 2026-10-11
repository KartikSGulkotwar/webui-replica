import json
import secrets

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlmodel import Session, col, delete, func, or_, select

from app.auth import ActiveUserDep
from app.db import SessionDep
from app.models import DEFAULT_TITLE, Conversation, Message, SharedChat, User, utcnow
from app.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
    RatingUpdate,
    ShareRead,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

SEARCH_LIMIT = 50
SNIPPET_RADIUS = 60


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


def get_share(session: Session, conversation_id: str) -> SharedChat | None:
    return session.exec(
        select(SharedChat).where(SharedChat.conversation_id == conversation_id)
    ).first()


def to_read(conversation: Conversation, shared: bool, snippet: str | None = None):
    return ConversationRead(
        **conversation.model_dump(exclude={"owner_id", "system_prompt"}),
        shared=shared,
        snippet=snippet,
    )


def to_detail(session: Session, conversation: Conversation) -> ConversationDetail:
    share = get_share(session, conversation.id)
    return ConversationDetail(
        **conversation.model_dump(exclude={"owner_id"}),
        shared=share is not None,
        share_id=share.id if share else None,
        messages=[
            MessageRead.model_validate(m, from_attributes=True)
            for m in list_messages(session, conversation.id)
        ],
    )


def like_pattern(text: str) -> str:
    """Case-insensitive LIKE pattern with %, _ and \\ in the query matched literally."""
    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def make_snippet(content: str, query: str) -> str:
    at = content.lower().find(query.lower())
    if at < 0:
        return content[: SNIPPET_RADIUS * 2]
    start = max(0, at - SNIPPET_RADIUS)
    end = min(len(content), at + len(query) + SNIPPET_RADIUS)
    text = " ".join(content[start:end].split())
    return ("…" if start > 0 else "") + text + ("…" if end < len(content) else "")


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    session: SessionDep,
    user: ActiveUserDep,
    q: str | None = Query(default=None, max_length=200),
    archived: bool = False,
) -> list[ConversationRead]:
    """Pinned first, then most recently updated. `q` searches titles and messages."""
    stmt = (
        select(Conversation)
        .where(Conversation.owner_id == user.id, Conversation.archived == archived)
        .order_by(col(Conversation.pinned).desc(), col(Conversation.updated_at).desc())
    )
    query = (q or "").strip()
    if query:
        pattern = like_pattern(query)
        in_messages = select(Message.conversation_id).where(
            func.lower(Message.content).like(pattern, escape="\\")
        )
        stmt = stmt.where(
            or_(
                func.lower(Conversation.title).like(pattern, escape="\\"),
                col(Conversation.id).in_(in_messages),
            )
        ).limit(SEARCH_LIMIT)
    conversations = list(session.exec(stmt).all())
    ids = [c.id for c in conversations]

    shared = set(
        session.exec(
            select(SharedChat.conversation_id).where(col(SharedChat.conversation_id).in_(ids))
        )
    )
    snippets: dict[str, str] = {}
    if query and ids:
        matches = session.exec(
            select(Message)
            .where(
                col(Message.conversation_id).in_(ids),
                func.lower(Message.content).like(like_pattern(query), escape="\\"),
            )
            .order_by(col(Message.id))
        )
        for m in matches:
            snippets.setdefault(m.conversation_id, make_snippet(m.content, query))
    return [to_read(c, c.id in shared, snippets.get(c.id)) for c in conversations]


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate, session: SessionDep, user: ActiveUserDep
) -> ConversationRead:
    conversation = Conversation(
        title=(body.title or "").strip() or DEFAULT_TITLE,
        system_prompt=(body.system_prompt or "").strip() or None,
        owner_id=user.id,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return to_read(conversation, shared=False)


# Declared before /{conversation_id} so "export" isn't taken as an ID.
@router.get("/export", response_model=list[ConversationDetail])
def export_all(session: SessionDep, user: ActiveUserDep) -> list[ConversationDetail]:
    """Every conversation (archived too) with its messages, for backup."""
    stmt = (
        select(Conversation)
        .where(Conversation.owner_id == user.id)
        .order_by(col(Conversation.created_at))
    )
    return [to_detail(session, c) for c in session.exec(stmt).all()]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, session: SessionDep, user: ActiveUserDep
) -> ConversationDetail:
    return to_detail(session, get_conversation_or_404(session, conversation_id, user))


@router.patch("/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: str, body: ConversationUpdate, session: SessionDep, user: ActiveUserDep
) -> ConversationRead:
    conversation = get_conversation_or_404(session, conversation_id, user)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Title cannot be blank")
        conversation.title = title
    if body.system_prompt is not None:
        conversation.system_prompt = body.system_prompt.strip() or None
    if body.pinned is not None:
        conversation.pinned = body.pinned
    if body.archived is not None:
        conversation.archived = body.archived
        if body.archived:
            conversation.pinned = False
    # Metadata changes don't touch updated_at, so pinning or renaming
    # doesn't reshuffle the sidebar.
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return to_read(conversation, shared=get_share(session, conversation.id) is not None)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, session: SessionDep, user: ActiveUserDep) -> Response:
    conversation = get_conversation_or_404(session, conversation_id, user)
    # Explicit deletes: SQLite doesn't enforce ON DELETE CASCADE by default.
    session.exec(delete(Message).where(col(Message.conversation_id) == conversation_id))
    session.exec(delete(SharedChat).where(col(SharedChat.conversation_id) == conversation_id))
    session.delete(conversation)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{conversation_id}/messages/{message_id}/rating", response_model=MessageRead)
def rate_message(
    conversation_id: str,
    message_id: int,
    body: RatingUpdate,
    session: SessionDep,
    user: ActiveUserDep,
) -> MessageRead:
    get_conversation_or_404(session, conversation_id, user)
    message = session.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Only replies can be rated")
    message.rating = body.rating
    message.rating_comment = (body.comment or "").strip() or None if body.rating else None
    session.add(message)
    session.commit()
    session.refresh(message)
    return MessageRead.model_validate(message, from_attributes=True)


@router.post("/{conversation_id}/share", response_model=ShareRead)
def share_conversation(conversation_id: str, session: SessionDep, user: ActiveUserDep) -> ShareRead:
    """Create the public snapshot, or refresh it with the current messages."""
    conversation = get_conversation_or_404(session, conversation_id, user)
    snapshot = json.dumps(
        [
            {"role": m.role, "content": m.content, "model_id": m.model_id}
            for m in list_messages(session, conversation.id)
            if m.role != "system"
        ]
    )
    share = get_share(session, conversation.id)
    if share is None:
        share = SharedChat(
            id=secrets.token_urlsafe(16),
            conversation_id=conversation.id,
            title=conversation.title,
            messages_json=snapshot,
        )
    else:
        share.title = conversation.title
        share.messages_json = snapshot
        share.updated_at = utcnow()
    session.add(share)
    session.commit()
    session.refresh(share)
    return ShareRead(share_id=share.id, created_at=share.created_at, updated_at=share.updated_at)


@router.delete("/{conversation_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def unshare_conversation(
    conversation_id: str, session: SessionDep, user: ActiveUserDep
) -> Response:
    get_conversation_or_404(session, conversation_id, user)
    session.exec(delete(SharedChat).where(col(SharedChat.conversation_id) == conversation_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

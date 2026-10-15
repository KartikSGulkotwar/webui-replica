from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from app.ai_text import pick_model, stream_completion, with_persona
from app.auth import ActiveUserDep, AdminUserDep
from app.catalog import ARENA_MODEL_ID
from app.db import SessionDep
from app.models import Channel, ChannelMessage, ChannelReaction, User, utcnow
from app.providers.registry import RegistryDep
from app.ratelimit import limit_chat
from app.schemas import (
    ChannelAiRequest,
    ChannelMessageEdit,
    ChannelMessagePage,
    ChannelMessageRead,
    ChannelMessageWrite,
    ChannelRead,
    ChannelWrite,
    ChatMessage,
    ReactionSummary,
    ReactionToggle,
)

router = APIRouter(prefix="/api/channels", tags=["channels"])

PAGE = 50
AI_CONTEXT_MESSAGES = 30
# Polls ask for changes since their last answer; overlap a little so a change
# committed while the previous poll ran isn't missed (clients merge by id).
POLL_OVERLAP = timedelta(seconds=2)


def get_channel_or_404(session: Session, channel_id: str) -> Channel:
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


def get_message_or_404(session: Session, channel_id: str, message_id: int) -> ChannelMessage:
    message = session.get(ChannelMessage, message_id)
    if message is None or message.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


def clean_name(name: str) -> str:
    """Channel names look like #general: lowercase, dashes for spaces."""
    slug = "-".join(name.strip().lower().lstrip("#").split())
    if not slug:
        raise HTTPException(status_code=422, detail="The channel needs a name")
    return slug[:80]


def reads(
    session: Session, messages: list[ChannelMessage], viewer: User
) -> list[ChannelMessageRead]:
    """Messages with author names and reaction counts."""
    ids = [m.id for m in messages if m.id is not None]
    user_ids = {m.user_id for m in messages if m.user_id}
    names = (
        dict(session.exec(select(User.id, User.name).where(col(User.id).in_(user_ids))).all())
        if user_ids
        else {}
    )
    reactions: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    if ids:
        for r in session.exec(
            select(ChannelReaction).where(col(ChannelReaction.message_id).in_(ids))
        ):
            reactions[r.message_id][r.emoji].append(r.user_id)
    out = []
    for m in messages:
        if m.model_id:
            author = m.model_id.split(":", 1)[-1]
        else:
            author = names.get(m.user_id or "", "Deleted user")
        out.append(
            ChannelMessageRead(
                id=m.id or 0,
                channel_id=m.channel_id,
                user_id=m.user_id,
                author=author,
                model_id=m.model_id,
                content="" if m.deleted else m.content,
                reply_to=m.reply_to,
                deleted=m.deleted,
                edited=m.edited_at is not None,
                reactions=[
                    ReactionSummary(emoji=e, count=len(who), mine=viewer.id in who)
                    for e, who in reactions[m.id or 0].items()
                ]
                if not m.deleted
                else [],
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
        )
    return out


# --- channels ------------------------------------------------------------------------


@router.get("", response_model=list[ChannelRead])
def list_channels(session: SessionDep, user: ActiveUserDep) -> list[Channel]:
    return list(session.exec(select(Channel).order_by(col(Channel.name))))


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def create_channel(body: ChannelWrite, session: SessionDep, admin: AdminUserDep) -> Channel:
    name = clean_name(body.name)
    if session.exec(select(Channel).where(Channel.name == name)).first():
        raise HTTPException(status_code=409, detail=f"#{name} already exists")
    channel = Channel(name=name, description=body.description.strip(), created_by=admin.id)
    session.add(channel)
    session.commit()
    session.refresh(channel)
    return channel


@router.patch("/{channel_id}", response_model=ChannelRead)
def update_channel(
    channel_id: str, body: ChannelWrite, session: SessionDep, admin: AdminUserDep
) -> Channel:
    channel = get_channel_or_404(session, channel_id)
    name = clean_name(body.name)
    clash = session.exec(select(Channel).where(Channel.name == name)).first()
    if clash and clash.id != channel.id:
        raise HTTPException(status_code=409, detail=f"#{name} already exists")
    channel.name, channel.description = name, body.description.strip()
    session.add(channel)
    session.commit()
    session.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: str, session: SessionDep, admin: AdminUserDep) -> Response:
    channel = get_channel_or_404(session, channel_id)
    ids = select(ChannelMessage.id).where(ChannelMessage.channel_id == channel.id)
    # Explicit deletes: SQLite doesn't enforce ON DELETE CASCADE by default.
    session.exec(delete(ChannelReaction).where(col(ChannelReaction.message_id).in_(ids)))
    session.exec(delete(ChannelMessage).where(ChannelMessage.channel_id == channel.id))
    session.delete(channel)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- messages ------------------------------------------------------------------------


@router.get("/{channel_id}/messages", response_model=ChannelMessagePage)
def list_messages(
    channel_id: str,
    session: SessionDep,
    user: ActiveUserDep,
    before: int | None = None,
    since: datetime | None = None,
    limit: int = Query(default=PAGE, ge=1, le=100),
) -> ChannelMessagePage:
    """The latest page (or the page `before` a message id), oldest first. With
    `since`, every message created or changed since then (for polling)."""
    get_channel_or_404(session, channel_id)
    now = utcnow()
    stmt = select(ChannelMessage).where(ChannelMessage.channel_id == channel_id)
    if since is not None:
        stmt = stmt.where(ChannelMessage.updated_at >= since - POLL_OVERLAP)
        messages = list(session.exec(stmt.order_by(col(ChannelMessage.id))))
        return ChannelMessagePage(messages=reads(session, messages, user), now=now)
    if before is not None:
        stmt = stmt.where(col(ChannelMessage.id) < before)
    newest = list(session.exec(stmt.order_by(col(ChannelMessage.id).desc()).limit(limit + 1)))
    has_more = len(newest) > limit
    messages = list(reversed(newest[:limit]))
    return ChannelMessagePage(messages=reads(session, messages, user), has_more=has_more, now=now)


@router.post(
    "/{channel_id}/messages",
    response_model=ChannelMessageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_chat)],
)
def post_message(
    channel_id: str, body: ChannelMessageWrite, session: SessionDep, user: ActiveUserDep
) -> ChannelMessageRead:
    get_channel_or_404(session, channel_id)
    if body.reply_to is not None:
        get_message_or_404(session, channel_id, body.reply_to)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="The message is empty")
    message = ChannelMessage(
        channel_id=channel_id, user_id=user.id, content=content, reply_to=body.reply_to
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return reads(session, [message], user)[0]


@router.patch("/{channel_id}/messages/{message_id}", response_model=ChannelMessageRead)
def edit_message(
    channel_id: str,
    message_id: int,
    body: ChannelMessageEdit,
    session: SessionDep,
    user: ActiveUserDep,
) -> ChannelMessageRead:
    message = get_message_or_404(session, channel_id, message_id)
    if message.user_id != user.id or message.model_id or message.deleted:
        raise HTTPException(status_code=403, detail="You can only edit your own messages")
    message.content = body.content.strip()
    message.edited_at = message.updated_at = utcnow()
    session.add(message)
    session.commit()
    session.refresh(message)
    return reads(session, [message], user)[0]


@router.delete("/{channel_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    channel_id: str, message_id: int, session: SessionDep, user: ActiveUserDep
) -> Response:
    """Your own messages (and model replies you asked for); admins can delete any."""
    message = get_message_or_404(session, channel_id, message_id)
    owner = message.user_id == user.id or (message.model_id and message.asked_by == user.id)
    if not owner and user.role != "admin":
        raise HTTPException(status_code=403, detail="You can only delete your own messages")
    # Kept as a placeholder so replies that quote it still make sense.
    message.deleted = True
    message.content = ""
    message.updated_at = utcnow()
    session.exec(delete(ChannelReaction).where(ChannelReaction.message_id == message.id))
    session.add(message)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{channel_id}/messages/{message_id}/reactions", response_model=ChannelMessageRead)
def toggle_reaction(
    channel_id: str,
    message_id: int,
    body: ReactionToggle,
    session: SessionDep,
    user: ActiveUserDep,
) -> ChannelMessageRead:
    message = get_message_or_404(session, channel_id, message_id)
    if message.deleted:
        raise HTTPException(status_code=400, detail="That message was deleted")
    existing = session.get(ChannelReaction, (message_id, user.id, body.emoji))
    if existing:
        session.delete(existing)
    else:
        session.add(ChannelReaction(message_id=message_id, user_id=user.id, emoji=body.emoji))
    message.updated_at = utcnow()  # so other people's polls pick it up
    session.add(message)
    session.commit()
    session.refresh(message)
    return reads(session, [message], user)[0]


# --- models in channels ----------------------------------------------------------------


def save_ai_reply(
    engine: Engine, channel_id: str, model_id: str, asked_by: str, reply_to: int, text: str
) -> None:
    if not text.strip():
        return
    with Session(engine) as session:
        if session.get(Channel, channel_id) is None:  # deleted meanwhile
            return
        session.add(
            ChannelMessage(
                channel_id=channel_id,
                model_id=model_id,
                asked_by=asked_by,
                content=text.strip(),
                reply_to=reply_to,
            )
        )
        session.commit()


@router.post("/{channel_id}/ai", dependencies=[Depends(limit_chat)])
def ask_model(
    channel_id: str,
    body: ChannelAiRequest,
    session: SessionDep,
    registry: RegistryDep,
    user: ActiveUserDep,
) -> StreamingResponse:
    """A model answers the message that mentioned it, seeing the recent
    conversation. Streams to the asker; saved for everyone when finished."""
    channel = get_channel_or_404(session, channel_id)
    asked = get_message_or_404(session, channel_id, body.message_id)
    if asked.user_id != user.id:
        raise HTTPException(status_code=403, detail="Mention a model in your own message")
    if body.model_id == ARENA_MODEL_ID:
        raise HTTPException(status_code=422, detail="The arena can't join channels")
    provider, resolved = pick_model(session, registry, user, body.model_id)

    recent = list(
        session.exec(
            select(ChannelMessage)
            .where(
                ChannelMessage.channel_id == channel_id,
                col(ChannelMessage.id) <= asked.id,
                col(ChannelMessage.deleted).is_(False),
            )
            .order_by(col(ChannelMessage.id).desc())
            .limit(AI_CONTEXT_MESSAGES)
        )
    )[::-1]
    lines = [f"{m.author}: {m.content}" for m in reads(session, recent, user)]
    name = body.model_id.split(":", 1)[-1]
    messages = with_persona(
        resolved,
        [
            ChatMessage(
                role="system",
                content=(
                    f"You are {name}, an AI assistant taking part in the #{channel.name} chat "
                    f"channel{': ' + channel.description if channel.description else ''}. "
                    f"Below are the latest messages, as 'Name: message'. {user.name} mentioned "
                    "you in the last one: reply to it directly, as a channel message (no name "
                    "prefix), concisely, using earlier messages as context."
                ),
            ),
            ChatMessage(role="user", content="\n\n".join(lines)),
        ],
    )

    async def save(text: str) -> None:
        await run_in_threadpool(
            save_ai_reply, session.get_bind(), channel_id, body.model_id, user.id, asked.id, text
        )

    return StreamingResponse(
        stream_completion(provider, resolved.model, messages, on_finish=save),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

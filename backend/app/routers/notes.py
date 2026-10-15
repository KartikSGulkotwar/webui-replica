from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, func, or_, select

from app.ai_text import pick_model, stream_completion, with_persona
from app.auth import ActiveUserDep
from app.db import SessionDep
from app.models import Conversation, Note, User, utcnow
from app.providers.registry import RegistryDep
from app.ratelimit import limit_chat
from app.schemas import (
    ChatMessage,
    ConversationRead,
    NoteAiRequest,
    NoteCreate,
    NoteRead,
    NoteSummary,
    NoteUpdate,
)

router = APIRouter(prefix="/api/notes", tags=["notes"])

MAX_NOTES = 500
SNIPPET_CHARS = 140

INSTRUCTIONS = {
    "improve": (
        "Improve this text: fix grammar and spelling, make it clearer and better organised, "
        "and keep the author's meaning, facts and voice. Keep markdown formatting. Reply with "
        "the improved text only, no preamble."
    ),
    "summarize": (
        "Summarize this text as a few concise markdown bullet points covering the key points "
        "and any decisions or action items. Reply with the summary only."
    ),
    "continue": (
        "Continue writing this text from where it ends, in the same style and format, for one "
        "or two paragraphs. Reply with only the new text, not what's already written."
    ),
}


def get_note_or_404(session: Session, note_id: str, user: User) -> Note:
    note = session.get(Note, note_id)
    if note is None or note.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def to_read(n: Note) -> NoteRead:
    return NoteRead(**n.model_dump(exclude={"owner_id"}))


def snippet(content: str) -> str:
    flat = " ".join(content.replace("#", " ").split())
    return flat[:SNIPPET_CHARS] + ("…" if len(flat) > SNIPPET_CHARS else "")


@router.get("", response_model=list[NoteSummary])
def list_notes(
    session: SessionDep, user: ActiveUserDep, q: str = Query(default="", max_length=200)
) -> list[NoteSummary]:
    stmt = select(Note).where(Note.owner_id == user.id)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Note.title).like(like), func.lower(Note.content).like(like))
        )
    stmt = stmt.order_by(col(Note.pinned).desc(), col(Note.updated_at).desc())
    return [
        NoteSummary(
            id=n.id,
            title=n.title,
            snippet=snippet(n.content),
            pinned=n.pinned,
            updated_at=n.updated_at,
        )
        for n in session.exec(stmt)
    ]


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(body: NoteCreate, session: SessionDep, user: ActiveUserDep) -> NoteRead:
    count = session.exec(select(func.count()).select_from(Note).where(Note.owner_id == user.id))
    if count.one() >= MAX_NOTES:
        raise HTTPException(status_code=409, detail=f"You can keep up to {MAX_NOTES} notes")
    note = Note(owner_id=user.id, title=body.title.strip(), content=body.content)
    session.add(note)
    session.commit()
    session.refresh(note)
    return to_read(note)


@router.get("/{note_id}", response_model=NoteRead)
def read_note(note_id: str, session: SessionDep, user: ActiveUserDep) -> NoteRead:
    return to_read(get_note_or_404(session, note_id, user))


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: str, body: NoteUpdate, session: SessionDep, user: ActiveUserDep
) -> NoteRead:
    note = get_note_or_404(session, note_id, user)
    if body.title is not None:
        note.title = body.title.strip()
    if body.content is not None:
        note.content = body.content
    if body.pinned is not None:
        note.pinned = body.pinned
    note.updated_at = utcnow()
    session.add(note)
    session.commit()
    session.refresh(note)
    return to_read(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, session: SessionDep, user: ActiveUserDep) -> Response:
    session.delete(get_note_or_404(session, note_id, user))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{note_id}/ai", dependencies=[Depends(limit_chat)])
def note_ai(
    note_id: str,
    body: NoteAiRequest,
    session: SessionDep,
    registry: RegistryDep,
    user: ActiveUserDep,
) -> StreamingResponse:
    """Improve, summarize or continue the note (or a selection), streamed as SSE."""
    note = get_note_or_404(session, note_id, user)
    text = (body.text if body.text is not None else note.content).strip()
    if not text:
        raise HTTPException(status_code=422, detail="The note is empty")
    if body.action == "custom":
        if not (body.instruction or "").strip():
            raise HTTPException(status_code=422, detail="Say what to do with the text")
        instruction = (
            f"{body.instruction.strip()}\n\nReply with the resulting text only, in markdown."  # type: ignore[union-attr]
        )
    else:
        instruction = INSTRUCTIONS[body.action]
    provider, resolved = pick_model(session, registry, user, body.model_id)
    # The title is context only; the text goes in as-is, so nothing extra (a
    # heading, wrapper tags) gets copied into the result.
    if note.title:
        instruction += f' (The note is titled "{note.title}"; don\'t repeat the title.)'
    messages = with_persona(
        resolved,
        [
            ChatMessage(role="system", content=instruction),
            ChatMessage(role="user", content=text),
        ],
    )
    return StreamingResponse(
        stream_completion(provider, resolved.model, messages),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{note_id}/chat", response_model=ConversationRead, status_code=201)
def chat_about_note(note_id: str, session: SessionDep, user: ActiveUserDep) -> ConversationRead:
    """Start a chat that has the note as context."""
    note = get_note_or_404(session, note_id, user)
    name = note.title or "Untitled note"
    conversation = Conversation(
        owner_id=user.id,
        title=f"About: {name}"[:200],
        system_prompt=(
            f'The user wants to talk about their note "{name}". Here it is:\n\n'
            f"<note>\n{note.content[:50_000]}\n</note>"
        ),
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return ConversationRead.model_validate(conversation, from_attributes=True)

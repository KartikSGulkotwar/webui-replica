"""Facts users ask the assistant to remember, and the ones a reply gets to see."""

from sqlmodel import Session, col, select

from app.models import Memory, User, utcnow
from app.rag.search import Candidate, bm25_rank

MAX_MEMORIES = 200  # per user
MAX_CHARS = 1000  # per memory
SHOW_ALL_UP_TO = 15  # with this many or fewer, every memory goes to the model
TOP_MATCHES = 8  # otherwise: the best keyword matches for the message...
RECENT = 3  # ...plus the newest ones (general preferences rarely share words)


class MemoryLimitError(ValueError):
    pass


def list_memories(session: Session, user_id: str) -> list[Memory]:
    stmt = (
        select(Memory)
        .where(Memory.owner_id == user_id)
        .order_by(col(Memory.created_at).desc(), col(Memory.id).desc())
    )
    return list(session.exec(stmt))


def add_memory(session: Session, user_id: str, content: str) -> Memory:
    content = " ".join(content.split())[:MAX_CHARS]
    if not content:
        raise ValueError("A memory can't be empty")
    existing = list_memories(session, user_id)
    duplicate = next((m for m in existing if m.content.lower() == content.lower()), None)
    if duplicate is not None:
        return duplicate
    if len(existing) >= MAX_MEMORIES:
        raise MemoryLimitError(f"You've reached {MAX_MEMORIES} memories. Delete some to add more.")
    memory = Memory(owner_id=user_id, content=content)
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory


def update_memory(session: Session, memory: Memory, content: str) -> Memory:
    content = " ".join(content.split())[:MAX_CHARS]
    if not content:
        raise ValueError("A memory can't be empty")
    memory.content = content
    memory.updated_at = utcnow()
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory


def relevant_memories(session: Session, user: User, message: str) -> list[Memory]:
    """The memories a reply to `message` should see, oldest first."""
    if not user.memory_enabled:
        return []
    memories = list_memories(session, user.id)  # newest first
    if len(memories) > SHOW_ALL_UP_TO:
        by_id = {m.id: m for m in memories}
        ranked = bm25_rank(message, [Candidate(m.id or 0, m.content) for m in memories])
        keep = set(ranked[:TOP_MATCHES]) | {m.id for m in memories[:RECENT]}
        memories = [by_id[i] for i in by_id if i in keep]
    return sorted(memories, key=lambda m: (m.created_at, m.id or 0))


def memory_context(memories: list[Memory]) -> str:
    lines = "\n".join(f"- {m.content} (saved {m.updated_at:%Y-%m-%d})" for m in memories)
    return (
        "The user asked you to remember these things about them. Use them when they're "
        "relevant to the request; don't bring them up otherwise, and don't say you were "
        "told them unless asked.\n<memories>\n" + lines + "\n</memories>"
    )

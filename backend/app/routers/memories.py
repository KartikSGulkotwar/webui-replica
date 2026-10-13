from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import delete

from app.auth import ActiveUserDep
from app.db import SessionDep
from app.memory import MemoryLimitError, add_memory, list_memories, update_memory
from app.models import Memory
from app.schemas import MemoryList, MemoryRead, MemorySettings, MemoryWrite

router = APIRouter(prefix="/api/memories", tags=["memory"])


def to_read(m: Memory) -> MemoryRead:
    return MemoryRead(
        id=m.id or 0, content=m.content, created_at=m.created_at, updated_at=m.updated_at
    )


def get_memory_or_404(session, memory_id: int, user_id: str) -> Memory:
    memory = session.get(Memory, memory_id)
    if memory is None or memory.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.get("", response_model=MemoryList)
def read_memories(session: SessionDep, user: ActiveUserDep) -> MemoryList:
    return MemoryList(
        enabled=user.memory_enabled,
        memories=[to_read(m) for m in list_memories(session, user.id)],
    )


@router.put("/settings", response_model=MemorySettings)
def write_settings(body: MemorySettings, session: SessionDep, user: ActiveUserDep):
    user.memory_enabled = body.enabled
    session.add(user)
    session.commit()
    return MemorySettings(enabled=user.memory_enabled)


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
def create_memory(body: MemoryWrite, session: SessionDep, user: ActiveUserDep) -> MemoryRead:
    try:
        return to_read(add_memory(session, user.id, body.content))
    except MemoryLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{memory_id}", response_model=MemoryRead)
def edit_memory(
    memory_id: int, body: MemoryWrite, session: SessionDep, user: ActiveUserDep
) -> MemoryRead:
    memory = get_memory_or_404(session, memory_id, user.id)
    try:
        return to_read(update_memory(session, memory, body.content))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: int, session: SessionDep, user: ActiveUserDep) -> Response:
    session.delete(get_memory_or_404(session, memory_id, user.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_memories(session: SessionDep, user: ActiveUserDep) -> Response:
    session.exec(delete(Memory).where(Memory.owner_id == user.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

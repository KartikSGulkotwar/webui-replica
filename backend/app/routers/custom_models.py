import json

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, col, select

from app.auth import ActiveUserDep
from app.catalog import PERSONA, hidden_model_ids, provider_models, visible_custom_models
from app.db import SessionDep
from app.models import CustomModel, KnowledgeCollection, User, utcnow
from app.providers.base import split_model_id
from app.schemas import AttachmentRead, CustomModelRead, CustomModelWrite
from app.seed import slugify
from app.tools.registry import TOOLS

router = APIRouter(prefix="/api/custom-models", tags=["custom models"])


def to_read(session: Session, c: CustomModel, user: User) -> CustomModelRead:
    ids = json.loads(c.knowledge_json)
    names = dict(
        session.exec(
            select(KnowledgeCollection.id, KnowledgeCollection.name).where(
                col(KnowledgeCollection.id).in_(ids), KnowledgeCollection.owner_id == c.owner_id
            )
        ).all()
    )
    return CustomModelRead(
        **c.model_dump(exclude={"owner_id", "knowledge_json", "tools_json"}),
        tool_ids=json.loads(c.tools_json),
        model_id=f"{PERSONA}:{c.id}",
        knowledge=[
            AttachmentRead(kind="collection", id=i, name=names[i]) for i in ids if i in names
        ],
        is_owner=c.owner_id == user.id,
    )


def get_editable(session: Session, model_id: str, user: User) -> CustomModel:
    c = session.get(CustomModel, model_id)
    visible = c is not None and (c.owner_id == user.id or c.visibility == "public")
    if not visible:
        raise HTTPException(status_code=404, detail="Custom model not found")
    # Owners edit their own; admins may also edit public ones.
    if c.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the creator can change this model")
    return c


def unique_id(session: Session, name: str) -> str:
    base = slugify(name)[:56]
    candidate, n = base, 2
    while session.get(CustomModel, candidate) is not None:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


async def validate(
    request: Request, session: Session, body: CustomModelWrite, owner: User, editor: User
) -> None:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be blank")
    if body.visibility == "public" and editor.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can share a model with everyone")
    try:
        provider_id, _ = split_model_id(body.base_model_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if provider_id == PERSONA:
        raise HTTPException(
            status_code=422, detail="A custom model can't be based on another custom model"
        )
    registry = request.app.state.registry
    await run_in_threadpool(registry.sync, session)
    models, _ = await provider_models(registry)
    if body.base_model_id not in {m.id for m in models}:
        raise HTTPException(status_code=422, detail="Base model isn't available right now")
    if body.base_model_id in hidden_model_ids(session) and editor.role != "admin":
        raise HTTPException(status_code=422, detail="Base model isn't available")
    unknown = set(body.tool_ids) - set(TOOLS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown tool: {sorted(unknown)[0]}")
    if body.knowledge_ids:
        owned = set(
            session.exec(
                select(KnowledgeCollection.id).where(
                    col(KnowledgeCollection.id).in_(body.knowledge_ids),
                    KnowledgeCollection.owner_id == owner.id,
                )
            )
        )
        if owned != set(body.knowledge_ids):
            raise HTTPException(status_code=404, detail="Knowledge base not found")


def apply(c: CustomModel, body: CustomModelWrite) -> None:
    c.name = body.name.strip()
    c.description = body.description.strip()
    c.emoji = body.emoji.strip() or "🤖"
    c.base_model_id = body.base_model_id
    c.system_prompt = body.system_prompt.strip()
    c.knowledge_json = json.dumps(list(dict.fromkeys(body.knowledge_ids)))
    c.tools_json = json.dumps(list(dict.fromkeys(body.tool_ids)))
    c.visibility = body.visibility
    c.updated_at = utcnow()


@router.get("", response_model=list[CustomModelRead])
def list_custom_models(session: SessionDep, user: ActiveUserDep) -> list[CustomModelRead]:
    return [to_read(session, c, user) for c in visible_custom_models(session, user)]


@router.post("", response_model=CustomModelRead, status_code=status.HTTP_201_CREATED)
async def create_custom_model(
    body: CustomModelWrite, request: Request, session: SessionDep, user: ActiveUserDep
) -> CustomModelRead:
    await validate(request, session, body, owner=user, editor=user)
    c = CustomModel(id=unique_id(session, body.name), owner_id=user.id, name="", base_model_id="")
    apply(c, body)
    session.add(c)
    session.commit()
    session.refresh(c)
    return to_read(session, c, user)


@router.get("/{model_id}", response_model=CustomModelRead)
def get_custom_model(model_id: str, session: SessionDep, user: ActiveUserDep) -> CustomModelRead:
    c = session.get(CustomModel, model_id)
    if c is None or (c.owner_id != user.id and c.visibility != "public"):
        raise HTTPException(status_code=404, detail="Custom model not found")
    return to_read(session, c, user)


@router.put("/{model_id}", response_model=CustomModelRead)
async def update_custom_model(
    model_id: str,
    body: CustomModelWrite,
    request: Request,
    session: SessionDep,
    user: ActiveUserDep,
) -> CustomModelRead:
    c = get_editable(session, model_id, user)
    owner = session.get(User, c.owner_id) or user
    await validate(request, session, body, owner=owner, editor=user)
    apply(c, body)
    session.add(c)
    session.commit()
    session.refresh(c)
    return to_read(session, c, user)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_model(model_id: str, session: SessionDep, user: ActiveUserDep) -> Response:
    session.delete(get_editable(session, model_id, user))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

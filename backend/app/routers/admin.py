import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlmodel import col, delete, func, select

from app.app_settings import get_admin_settings, save_admin_settings
from app.auth import AdminUserDep
from app.catalog import provider_models
from app.db import SessionDep
from app.models import (
    Conversation,
    ConversationAttachment,
    CustomModel,
    Document,
    DocumentChunk,
    KnowledgeCollection,
    Message,
    ModelSetting,
    OAuthAccount,
    SharedChat,
    User,
)
from app.providers.base import ProviderError
from app.rag.embed import embed
from app.rag.service import (
    embedding_config,
    load_embedding_settings,
    reindex_all,
    save_embedding_settings,
)
from app.routers.auth import to_read
from app.schemas import (
    AdminModelRead,
    AdminModelUpdate,
    AdminSettings,
    AdminUserUpdate,
    EmbeddingSettingsRead,
    EmbeddingSettingsUpdate,
    UserRead,
)

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
    session.exec(
        delete(ConversationAttachment).where(
            col(ConversationAttachment.conversation_id).in_(conversation_ids)
        )
    )
    document_ids = select(Document.id).where(Document.owner_id == user.id)
    session.exec(delete(DocumentChunk).where(col(DocumentChunk.document_id).in_(document_ids)))
    session.exec(delete(Document).where(Document.owner_id == user.id))
    session.exec(delete(KnowledgeCollection).where(KnowledgeCollection.owner_id == user.id))
    session.exec(delete(CustomModel).where(CustomModel.owner_id == user.id))
    session.exec(delete(Conversation).where(Conversation.owner_id == user.id))
    session.exec(delete(OAuthAccount).where(OAuthAccount.user_id == user.id))
    session.delete(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings", response_model=AdminSettings)
def read_settings(request: Request, session: SessionDep, admin: AdminUserDep) -> AdminSettings:
    return get_admin_settings(session, request.app.state.settings)


@router.put("/settings", response_model=AdminSettings)
def write_settings(
    body: AdminSettings, request: Request, session: SessionDep, admin: AdminUserDep
) -> AdminSettings:
    try:
        return save_admin_settings(session, body, request.app.state.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- documents / embeddings -----------------------------------------------------


def embedding_read(request: Request, session) -> EmbeddingSettingsRead:
    settings = request.app.state.settings
    stored = load_embedding_settings(session, settings)
    config = embedding_config(session, settings, request.app.state.cipher)
    total = session.exec(select(func.count()).select_from(DocumentChunk)).one()
    embedded = (
        session.exec(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.embedding_model == config.key)
        ).one()
        if config.enabled
        else 0
    )
    return EmbeddingSettingsRead(
        engine=config.engine if config.engine in ("ollama", "openai") else "",
        base_url=config.base_url,
        model=config.model,
        has_key=bool(stored.get("api_key_encrypted") or stored.get("env_api_key")),
        embedded_chunks=embedded,
        total_chunks=total,
    )


@router.get("/embeddings", response_model=EmbeddingSettingsRead)
def read_embeddings(
    request: Request, session: SessionDep, admin: AdminUserDep
) -> EmbeddingSettingsRead:
    return embedding_read(request, session)


@router.put("/embeddings", response_model=EmbeddingSettingsRead)
def write_embeddings(
    body: EmbeddingSettingsUpdate, request: Request, session: SessionDep, admin: AdminUserDep
) -> EmbeddingSettingsRead:
    settings = request.app.state.settings
    stored = load_embedding_settings(session, settings)
    values = {
        "engine": body.engine,
        "base_url": body.base_url.strip().rstrip("/"),
        "model": body.model.strip(),
        "api_key_encrypted": stored.get("api_key_encrypted"),
        "env_api_key": stored.get("env_api_key", False),
    }
    if body.engine and (not values["base_url"] or not values["model"]):
        raise HTTPException(status_code=422, detail="Base URL and model are required")
    if body.api_key is not None:
        key = body.api_key.strip()
        try:
            values["api_key_encrypted"] = request.app.state.cipher.encrypt(key) if key else None
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        values["env_api_key"] = False
    save_embedding_settings(session, values)
    return embedding_read(request, session)


@router.post("/embeddings/test")
async def test_embeddings(request: Request, session: SessionDep, admin: AdminUserDep) -> dict:
    """Embed a short text with the saved settings and report the vector size."""
    config = embedding_config(session, request.app.state.settings, request.app.state.cipher)
    if not config.enabled:
        raise HTTPException(status_code=400, detail="No embedding model is configured")
    http: httpx.AsyncClient = request.app.state.http
    try:
        [vector] = await embed(http, config, ["Hello, world"])
    except ProviderError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "dimensions": len(vector)}


@router.post("/embeddings/reindex")
async def reindex(request: Request, session: SessionDep, admin: AdminUserDep) -> dict:
    """Re-embed every document chunk with the current model (after changing it)."""
    config = embedding_config(session, request.app.state.settings, request.app.state.cipher)
    try:
        count = await reindex_all(session, request.app.state.http, config)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"reindexed_chunks": count}


# --- models (visibility and names) ----------------------------------------------------


@router.get("/models", response_model=list[AdminModelRead])
async def list_all_models(
    request: Request, session: SessionDep, admin: AdminUserDep
) -> list[AdminModelRead]:
    """Every provider model, including hidden ones, with its admin settings."""
    registry = request.app.state.registry
    registry.sync(session)
    models, statuses = await provider_models(registry)
    settings = {s.model_id: s for s in session.exec(select(ModelSetting))}
    ok = {s.id: s.ok for s in statuses}
    rows = [
        AdminModelRead(
            id=m.id,
            name=m.name,
            display_name=settings[m.id].display_name if m.id in settings else None,
            hidden=settings[m.id].hidden if m.id in settings else False,
            provider_id=m.provider_id,
            provider_name=m.provider_name,
            provider_ok=ok.get(m.provider_id, False),
        )
        for m in models
    ]
    return sorted(rows, key=lambda r: (r.provider_name.lower(), r.name.lower()))


@router.put("/models", status_code=status.HTTP_204_NO_CONTENT)
def update_model(body: AdminModelUpdate, session: SessionDep, admin: AdminUserDep) -> Response:
    """Hide/show a model or rename it. Settings for unknown IDs are kept, so a
    model that's temporarily offline keeps its settings."""
    display = (body.display_name or "").strip() or None
    row = session.get(ModelSetting, body.model_id)
    if not body.hidden and display is None:
        if row is not None:
            session.delete(row)
    else:
        row = row or ModelSetting(model_id=body.model_id)
        row.hidden, row.display_name = body.hidden, display
        session.add(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from typing import Annotated

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, col, delete, func, select

from app.auth import ActiveUserDep
from app.db import SessionDep
from app.models import (
    ConversationAttachment,
    Document,
    DocumentChunk,
    KnowledgeCollection,
    User,
    utcnow,
)
from app.rag.extract import SUPPORTED, ExtractionError, extract
from app.rag.service import embedding_config, index_document
from app.schemas import (
    CollectionCreate,
    CollectionDetail,
    CollectionRead,
    CollectionUpdate,
    DocumentRead,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]


def doc_read(d: Document) -> DocumentRead:
    return DocumentRead.model_validate(d, from_attributes=True)


def get_collection_or_404(session: Session, collection_id: str, user: User) -> KnowledgeCollection:
    c = session.get(KnowledgeCollection, collection_id)
    if c is None or c.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return c


def get_document_or_404(session: Session, document_id: str, user: User) -> Document:
    d = session.get(Document, document_id)
    if d is None or d.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return d


def delete_documents(session: Session, document_ids: list[str]) -> None:
    # Explicit deletes: SQLite doesn't enforce ON DELETE CASCADE by default.
    session.exec(delete(DocumentChunk).where(col(DocumentChunk.document_id).in_(document_ids)))
    session.exec(
        delete(ConversationAttachment).where(
            ConversationAttachment.kind == "document",
            col(ConversationAttachment.ref_id).in_(document_ids),
        )
    )
    session.exec(delete(Document).where(col(Document.id).in_(document_ids)))


def collection_read(session: Session, c: KnowledgeCollection) -> CollectionRead:
    count = session.exec(
        select(func.count()).select_from(Document).where(Document.collection_id == c.id)
    ).one()
    return CollectionRead(**c.model_dump(exclude={"owner_id"}), document_count=count)


# --- collections ------------------------------------------------------------------


@router.get("/collections", response_model=list[CollectionRead])
def list_collections(session: SessionDep, user: ActiveUserDep) -> list[CollectionRead]:
    rows = session.exec(
        select(KnowledgeCollection)
        .where(KnowledgeCollection.owner_id == user.id)
        .order_by(col(KnowledgeCollection.updated_at).desc())
    )
    return [collection_read(session, c) for c in rows]


@router.post("/collections", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    body: CollectionCreate, session: SessionDep, user: ActiveUserDep
) -> CollectionRead:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be blank")
    c = KnowledgeCollection(owner_id=user.id, name=name, description=body.description.strip())
    session.add(c)
    session.commit()
    session.refresh(c)
    return collection_read(session, c)


@router.get("/collections/{collection_id}", response_model=CollectionDetail)
def get_collection(
    collection_id: str, session: SessionDep, user: ActiveUserDep
) -> CollectionDetail:
    c = get_collection_or_404(session, collection_id, user)
    docs = session.exec(
        select(Document).where(Document.collection_id == c.id).order_by(col(Document.created_at))
    ).all()
    return CollectionDetail(
        **collection_read(session, c).model_dump(), documents=[doc_read(d) for d in docs]
    )


@router.patch("/collections/{collection_id}", response_model=CollectionRead)
def update_collection(
    collection_id: str, body: CollectionUpdate, session: SessionDep, user: ActiveUserDep
) -> CollectionRead:
    c = get_collection_or_404(session, collection_id, user)
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=422, detail="Name cannot be blank")
        c.name = body.name.strip()
    if body.description is not None:
        c.description = body.description.strip()
    c.updated_at = utcnow()
    session.add(c)
    session.commit()
    session.refresh(c)
    return collection_read(session, c)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: str, session: SessionDep, user: ActiveUserDep) -> Response:
    c = get_collection_or_404(session, collection_id, user)
    doc_ids = list(session.exec(select(Document.id).where(Document.collection_id == c.id)))
    delete_documents(session, doc_ids)
    session.exec(
        delete(ConversationAttachment).where(
            ConversationAttachment.kind == "collection", ConversationAttachment.ref_id == c.id
        )
    )
    session.delete(c)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- documents --------------------------------------------------------------------


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    session: SessionDep,
    http: HttpDep,
    user: ActiveUserDep,
    file: Annotated[UploadFile, File()],
    collection_id: Annotated[str | None, Form()] = None,
) -> DocumentRead:
    """Extract, chunk, and index a file. Into a knowledge base if collection_id is
    given; otherwise it's a standalone document to attach to a chat."""
    settings = request.app.state.settings
    collection = get_collection_or_404(session, collection_id, user) if collection_id else None
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=413, detail=f"Files can be at most {settings.max_upload_mb} MB"
        )
    filename = (file.filename or "document").strip()[:255] or "document"
    try:
        pages = await run_in_threadpool(extract, filename, data)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=f"{filename}: {exc}") from exc

    document = Document(
        owner_id=user.id,
        collection_id=collection.id if collection else None,
        filename=filename,
        size_bytes=len(data),
    )
    session.add(document)
    session.flush()
    config = embedding_config(session, settings, request.app.state.cipher)
    document = await index_document(session, http, config, document, pages)
    if collection:
        collection.updated_at = utcnow()
        session.add(collection)
        session.commit()
    return doc_read(document)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: str, session: SessionDep, user: ActiveUserDep) -> DocumentRead:
    return doc_read(get_document_or_404(session, document_id, user))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, session: SessionDep, user: ActiveUserDep) -> Response:
    d = get_document_or_404(session, document_id, user)
    delete_documents(session, [d.id])
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/supported-types")
def supported_types() -> list[str]:
    return sorted(SUPPORTED)

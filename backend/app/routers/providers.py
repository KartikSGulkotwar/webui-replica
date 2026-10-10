from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, col, select

from app.crypto import EncryptionError, KeyCipher
from app.db import SessionDep
from app.models import Provider, utcnow
from app.providers.base import ProviderError
from app.providers.registry import PROVIDER_CLASSES, build_provider
from app.schemas import (
    ProviderCreate,
    ProviderHealth,
    ProviderRead,
    ProviderTest,
    ProviderUpdate,
)
from app.seed import slugify

router = APIRouter(prefix="/api/providers", tags=["providers"])


def get_cipher(request: Request) -> KeyCipher:
    return request.app.state.cipher


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


CipherDep = Annotated[KeyCipher, Depends(get_cipher)]
HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]


def require_writable(request: Request) -> None:
    if request.app.state.settings.providers_read_only:
        raise HTTPException(
            status_code=403, detail="Provider settings are read-only on this deployment"
        )


Writable = Depends(require_writable)


def to_read(row: Provider) -> ProviderRead:
    return ProviderRead(
        id=row.id,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        base_url=row.base_url,
        enabled=row.enabled,
        has_key=row.api_key_encrypted is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_or_404(session: Session, provider_id: str) -> Provider:
    row = session.get(Provider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return row


def encrypt_key(cipher: KeyCipher, key: str) -> str:
    try:
        return cipher.encrypt(key)
    except EncryptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def unique_id(session: Session, name: str) -> str:
    base = slugify(name)[:56]
    candidate, n = base, 2
    while session.get(Provider, candidate) is not None:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


@router.get("", response_model=list[ProviderRead])
def list_providers(session: SessionDep) -> list[ProviderRead]:
    rows = session.exec(select(Provider).order_by(col(Provider.created_at))).all()
    return [to_read(r) for r in rows]


@router.post(
    "",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Writable],
)
def create_provider(body: ProviderCreate, session: SessionDep, cipher: CipherDep) -> ProviderRead:
    key = (body.api_key or "").strip()
    row = Provider(
        id=unique_id(session, body.name),
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        api_key_encrypted=encrypt_key(cipher, key) if key else None,
        enabled=body.enabled,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_read(row)


@router.patch("/{provider_id}", response_model=ProviderRead, dependencies=[Writable])
def update_provider(
    provider_id: str, body: ProviderUpdate, session: SessionDep, cipher: CipherDep
) -> ProviderRead:
    row = get_or_404(session, provider_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be blank")
        row.name = name
    if body.base_url is not None:
        row.base_url = body.base_url
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.api_key is not None:
        key = body.api_key.strip()
        row.api_key_encrypted = encrypt_key(cipher, key) if key else None
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_read(row)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Writable])
def delete_provider(provider_id: str, session: SessionDep) -> Response:
    session.delete(get_or_404(session, provider_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{provider_id}/health", response_model=ProviderHealth)
async def provider_health(
    provider_id: str, session: SessionDep, cipher: CipherDep, http: HttpDep
) -> ProviderHealth:
    # Works for disabled providers too, so they can be checked before enabling.
    row = get_or_404(session, provider_id)
    try:
        provider = build_provider(row, http, cipher)
    except ProviderError as exc:
        return ProviderHealth(ok=False, error=str(exc))
    return await provider.health()


@router.post("/test", response_model=ProviderHealth, dependencies=[Writable])
async def test_connection(
    body: ProviderTest, session: SessionDep, cipher: CipherDep, http: HttpDep
) -> ProviderHealth:
    """Test unsaved form values. Writable-only: it makes the server call any URL."""
    api_key = body.api_key.strip() if body.api_key else None
    if api_key is None and body.provider_id:
        row = get_or_404(session, body.provider_id)
        if row.api_key_encrypted:
            try:
                api_key = cipher.decrypt(row.api_key_encrypted)
            except EncryptionError as exc:
                return ProviderHealth(ok=False, error=str(exc))
    cls = PROVIDER_CLASSES[body.kind]
    provider = cls(id="test", name="test", base_url=body.base_url, client=http, api_key=api_key)
    return await provider.health()

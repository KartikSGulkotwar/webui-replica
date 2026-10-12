import json
import os

import httpx
import pytest
import respx
from sqlmodel import Session, select

from app.db import make_engine
from app.models import Document, DocumentChunk, Provider
from app.rag.embed import EmbeddingConfig
from app.rag.service import retrieve
from tests.rag_helpers import make_pdf

OLLAMA = "http://ollama.test"
EMBED = "http://embed.test"

POLICY = (
    "Refund policy. Customers may request a full refund within 30 days of purchase. "
    "After 30 days, store credit is offered instead.\n\n"
    "Shipping policy. Orders ship within 2 business days. Shipping is free on orders over $50."
)


def upload(client, name: str, data: bytes, collection_id: str | None = None):
    form = {"collection_id": collection_id} if collection_id else {}
    return client.post("/api/knowledge/documents", files={"file": (name, data)}, data=form)


def new_collection(client, name="Company docs") -> str:
    resp = client.post(
        "/api/knowledge/collections", json={"name": name, "description": "HR + policies"}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def ollama_chat(session):
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()


def reply(text: str) -> bytes:
    lines = [
        {"message": {"content": text}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    return b"".join(json.dumps(x).encode() + b"\n" for x in lines)


def events(resp) -> list[dict]:
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


# --- collections & uploads ---------------------------------------------------------


def test_collection_crud(client) -> None:
    cid = new_collection(client)
    assert client.get("/api/knowledge/collections").json()[0]["document_count"] == 0
    upload(client, "policy.txt", POLICY.encode(), cid)
    detail = client.get(f"/api/knowledge/collections/{cid}").json()
    assert detail["document_count"] == 1 and detail["documents"][0]["filename"] == "policy.txt"
    assert (
        client.patch(f"/api/knowledge/collections/{cid}", json={"name": "Renamed"}).json()["name"]
        == "Renamed"
    )
    assert client.patch(f"/api/knowledge/collections/{cid}", json={"name": " "}).status_code == 422


def test_upload_pdf_indexes_chunks_with_pages(client, session) -> None:
    resp = upload(client, "report.pdf", make_pdf(["Alpha page text", "Beta page text"]))
    assert resp.status_code == 201
    doc = resp.json()
    assert (doc["page_count"], doc["chunk_count"], doc["collection_id"], doc["warning"]) == (
        2,
        2,
        None,
        None,
    )
    chunks = session.exec(select(DocumentChunk).order_by(DocumentChunk.position)).all()
    assert [(c.page, c.text, c.embedding) for c in chunks] == [
        (1, "Alpha page text", None),
        (2, "Beta page text", None),
    ]


def test_upload_rejections(client, settings) -> None:
    bad = upload(client, "virus.exe", b"MZ")
    assert bad.status_code == 422 and "virus.exe" in bad.json()["detail"]
    settings.max_upload_mb = 1
    big = upload(client, "big.txt", b"x" * (1024 * 1024 + 1))
    assert big.status_code == 413 and "1 MB" in big.json()["detail"]
    assert upload(client, "a.txt", b"hi", "missing-collection").status_code == 404


def test_documents_are_private(client, user_client) -> None:
    cid = new_collection(client)
    doc = upload(client, "policy.txt", POLICY.encode(), cid).json()
    assert user_client.get(f"/api/knowledge/collections/{cid}").status_code == 404
    assert user_client.get("/api/knowledge/collections").json() == []
    assert user_client.get(f"/api/knowledge/documents/{doc['id']}").status_code == 404
    assert user_client.delete(f"/api/knowledge/documents/{doc['id']}").status_code == 404
    assert upload(user_client, "x.txt", b"hi", cid).status_code == 404
    conv = user_client.post("/api/conversations", json={}).json()["id"]
    attach = user_client.put(
        f"/api/conversations/{conv}/attachments", json={"collection_ids": [cid]}
    )
    assert attach.status_code == 404


def test_deleting_removes_chunks_and_attachments(client, session) -> None:
    cid = new_collection(client)
    doc = upload(client, "policy.txt", POLICY.encode(), cid).json()
    solo = upload(client, "solo.txt", b"standalone notes").json()
    conv = client.post(
        "/api/conversations",
        json={"attachments": {"collection_ids": [cid], "document_ids": [solo["id"]]}},
    ).json()["id"]
    assert len(client.get(f"/api/conversations/{conv}").json()["attachments"]) == 2

    assert client.delete(f"/api/knowledge/documents/{solo['id']}").status_code == 204
    assert [a["kind"] for a in client.get(f"/api/conversations/{conv}").json()["attachments"]] == [
        "collection"
    ]
    assert client.delete(f"/api/knowledge/collections/{cid}").status_code == 204
    assert client.get(f"/api/conversations/{conv}").json()["attachments"] == []
    assert session.exec(select(DocumentChunk)).all() == []
    assert client.get(f"/api/knowledge/documents/{doc['id']}").status_code == 404


# --- chat with documents (keyword search) --------------------------------------------


@respx.mock
def test_chat_cites_attached_documents(client, ollama_chat) -> None:
    cid = new_collection(client)
    upload(client, "policy.txt", POLICY.encode(), cid)
    upload(client, "menu.txt", b"Lunch menu: soup, salad, sandwiches.", cid)
    route = respx.post(f"{OLLAMA}/api/chat").respond(content=reply("You have 30 days [1]."))
    conv = client.post(
        "/api/conversations",
        json={"system_prompt": "Be brief.", "attachments": {"collection_ids": [cid]}},
    ).json()["id"]

    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:m",
            "message": "How long do I have to get a refund?",
        },
    )

    evts = events(resp)
    sources = evts[0]["sources"]  # sent before the answer
    assert sources[0]["filename"] == "policy.txt" and sources[0]["n"] == 1
    assert "30 days" in sources[0]["text"]
    assert all("Lunch" not in s["text"] for s in sources)  # unrelated doc not retrieved

    sent = json.loads(route.calls.last.request.content)["messages"]
    assert sent[0] == {"role": "system", "content": "Be brief."}
    assert sent[1]["role"] == "system" and "[1] (policy.txt)" in sent[1]["content"]
    assert "Cite the excerpts" in sent[1]["content"]
    assert sent[-1] == {"role": "user", "content": "How long do I have to get a refund?"}

    saved = client.get(f"/api/conversations/{conv}").json()["messages"][-1]
    assert saved["sources"][0]["filename"] == "policy.txt"


@respx.mock
def test_chat_without_attachments_has_no_sources(client, ollama_chat) -> None:
    upload(client, "policy.txt", POLICY.encode())  # exists, but not attached
    route = respx.post(f"{OLLAMA}/api/chat").respond(content=reply("Hi"))
    conv = client.post("/api/conversations", json={}).json()["id"]
    resp = client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:m", "message": "refund?"},
    )
    assert "sources" not in events(resp)[0]
    assert all(
        m["role"] != "system" for m in json.loads(route.calls.last.request.content)["messages"]
    )
    assert client.get(f"/api/conversations/{conv}").json()["messages"][-1]["sources"] is None


@respx.mock
def test_pdf_sources_carry_page_numbers(client, ollama_chat) -> None:
    doc = upload(
        client, "handbook.pdf", make_pdf(["Vacation is 20 days per year", "Parking is in lot B"])
    ).json()
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("Lot B [1]"))
    conv = client.post(
        "/api/conversations", json={"attachments": {"document_ids": [doc["id"]]}}
    ).json()["id"]
    resp = client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:m", "message": "Where is parking?"},
    )
    first = events(resp)[0]["sources"][0]
    assert (first["filename"], first["page"], first["text"]) == (
        "handbook.pdf",
        2,
        "Parking is in lot B",
    )


def test_attachments_endpoint(client) -> None:
    cid = new_collection(client, "Zeta")
    doc = upload(client, "a.txt", b"alpha").json()
    conv = client.post("/api/conversations", json={}).json()["id"]
    got = client.put(
        f"/api/conversations/{conv}/attachments",
        json={"collection_ids": [cid], "document_ids": [doc["id"]]},
    ).json()
    assert [(a["kind"], a["name"]) for a in got] == [("collection", "Zeta"), ("document", "a.txt")]
    assert client.put(f"/api/conversations/{conv}/attachments", json={}).json() == []


# --- embeddings (hybrid search) -------------------------------------------------------


def fake_embed(request):
    """Deterministic toy embeddings: 'refund'-ish texts point one way, others another."""
    texts = json.loads(request.content)["input"]
    vecs = [
        [1.0, 0.0] if ("refund" in t.lower() or "money back" in t.lower()) else [0.0, 1.0]
        for t in texts
    ]
    return httpx.Response(200, json={"embeddings": vecs})


def configure_embeddings(client) -> None:
    resp = client.put(
        "/api/admin/embeddings", json={"engine": "ollama", "base_url": EMBED, "model": "toy-embed"}
    )
    assert resp.status_code == 200, resp.text


@respx.mock
def test_semantic_search_finds_paraphrases(client, ollama_chat) -> None:
    respx.post(f"{EMBED}/api/embed").mock(side_effect=fake_embed)
    configure_embeddings(client)
    doc = upload(client, "policy.txt", POLICY.encode()).json()
    assert doc["warning"] is None
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("ok"))
    conv = client.post(
        "/api/conversations", json={"attachments": {"document_ids": [doc["id"]]}}
    ).json()["id"]
    # No keyword overlap with "refund", but the toy embedding matches "money back".
    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:m",
            "message": "Can I get my money back?",
        },
    )
    assert "refund" in events(resp)[0]["sources"][0]["text"].lower()


@respx.mock
def test_embedding_failure_falls_back_to_keywords(client, ollama_chat) -> None:
    respx.post(f"{EMBED}/api/embed").respond(500, text="embedder down")
    configure_embeddings(client)
    doc = upload(client, "policy.txt", POLICY.encode()).json()
    assert "Keyword search still works" in doc["warning"]
    respx.post(f"{OLLAMA}/api/chat").respond(content=reply("ok"))
    conv = client.post(
        "/api/conversations", json={"attachments": {"document_ids": [doc["id"]]}}
    ).json()["id"]
    resp = client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "ollama:m", "message": "refund window?"},
    )
    assert events(resp)[0]["sources"][0]["filename"] == "policy.txt"


@respx.mock
def test_admin_embedding_settings_test_and_reindex(client, session) -> None:
    settings = client.get("/api/admin/embeddings").json()
    assert settings["engine"] == "" and settings["total_chunks"] == 0
    upload(client, "policy.txt", POLICY.encode())  # indexed without embeddings

    respx.post(f"{EMBED}/embeddings").mock(
        side_effect=lambda r: httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [0.1, 0.2, 0.3]}
                    for i, _ in enumerate(json.loads(r.content)["input"])
                ]
            },
        )
    )
    saved = client.put(
        "/api/admin/embeddings",
        json={
            "engine": "openai",
            "base_url": f"{EMBED}/",
            "model": "voyage-3",
            "api_key": "vk-secret",
        },
    ).json()
    assert saved["has_key"] is True and saved["base_url"] == EMBED and saved["embedded_chunks"] == 0
    assert "vk-secret" not in client.get("/api/admin/embeddings").text

    assert client.post("/api/admin/embeddings/test").json() == {"ok": True, "dimensions": 3}
    total = saved["total_chunks"]
    assert client.post("/api/admin/embeddings/reindex").json() == {"reindexed_chunks": total}
    assert client.get("/api/admin/embeddings").json()["embedded_chunks"] == total
    assert respx.calls.last.request.headers["authorization"] == "Bearer vk-secret"

    # Keep key when omitted; remove with "".
    assert client.put(
        "/api/admin/embeddings", json={"engine": "openai", "base_url": EMBED, "model": "voyage-3"}
    ).json()["has_key"]
    assert not client.put(
        "/api/admin/embeddings",
        json={"engine": "openai", "base_url": EMBED, "model": "voyage-3", "api_key": ""},
    ).json()["has_key"]
    bad = client.put(
        "/api/admin/embeddings", json={"engine": "ollama", "base_url": "", "model": ""}
    )
    assert bad.status_code == 422


def test_embedding_admin_is_admin_only(user_client) -> None:
    assert user_client.get("/api/admin/embeddings").status_code == 403
    assert user_client.post("/api/admin/embeddings/reindex").status_code == 403


def test_deleting_user_removes_their_documents(client, app, session) -> None:
    from fastapi.testclient import TestClient

    from tests.conftest import signup

    with TestClient(app) as other:
        user = signup(other, "docs@example.com")
        client.patch(f"/api/admin/users/{user['id']}", json={"role": "user"})
        cid = new_collection(other)
        upload(other, "mine.txt", b"private notes", cid)
        client.delete(f"/api/admin/users/{user['id']}")
    session.expire_all()
    assert (
        session.exec(select(Document)).all() == []
        and session.exec(select(DocumentChunk)).all() == []
    )


# --- pgvector -----------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="needs Postgres with pgvector")
async def test_vector_search_runs_in_pgvector(http) -> None:
    from app.db import run_migrations

    url = os.environ["TEST_POSTGRES_URL"]
    engine = make_engine(url)
    with engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    run_migrations(url)
    config = EmbeddingConfig("ollama", EMBED, "toy-embed")
    with Session(engine) as s, respx.mock:
        respx.post(f"{EMBED}/api/embed").mock(side_effect=fake_embed)
        s.add(Document(id="d1", owner_id="u1", filename="policy.txt"))
        s.add(Document(id="d2", owner_id="u1", filename="other.txt"))
        s.flush()
        s.add(
            DocumentChunk(
                document_id="d1",
                position=0,
                text="Refunds within 30 days",
                embedding=[1.0, 0.0],
                embedding_model=config.key,
            )
        )
        s.add(
            DocumentChunk(
                document_id="d1",
                position=1,
                text="Shipping in 2 days",
                embedding=[0.0, 1.0],
                embedding_model=config.key,
            )
        )
        s.add(
            DocumentChunk(
                document_id="d2",
                position=0,
                text="Refunds elsewhere",
                embedding=[1.0, 0.0],
                embedding_model=config.key,
            )
        )
        # A chunk from another embedding model must be ignored by vector search.
        s.add(
            DocumentChunk(
                document_id="d1",
                position=2,
                text="unrelated",
                embedding=[1.0, 0.0, 0.0],
                embedding_model="other:model",
            )
        )
        s.commit()
        assert s.get_bind().dialect.name == "postgresql"
        found = await retrieve(s, http, config, ["d1"], "Can I get my money back?")
        assert found[0].text == "Refunds within 30 days"
        assert all(f.document_id == "d1" for f in found) and "unrelated" not in [
            f.text for f in found
        ]
        stored = s.exec(
            select(DocumentChunk).where(
                DocumentChunk.position == 0, DocumentChunk.document_id == "d1"
            )
        ).one()
        assert stored.embedding == [1.0, 0.0]
    engine.dispose()

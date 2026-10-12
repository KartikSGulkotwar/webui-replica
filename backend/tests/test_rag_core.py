import httpx
import pytest
import respx

from app.providers.base import ProviderError
from app.rag.chunk import chunk_pages
from app.rag.embed import EmbeddingConfig, embed
from app.rag.extract import ExtractionError, Page, extract
from app.rag.search import (
    Candidate,
    bm25_rank,
    close_to_best,
    cosine,
    reciprocal_rank_fusion,
    tokenize,
)
from tests.rag_helpers import make_docx, make_pdf

# --- extraction -------------------------------------------------------------------


def test_pdf_keeps_page_numbers() -> None:
    pages = extract("report.pdf", make_pdf(["Revenue grew in Q1", "Costs fell in Q2"]))
    assert [(p.number, p.text) for p in pages] == [
        (1, "Revenue grew in Q1"),
        (2, "Costs fell in Q2"),
    ]


def test_pdf_without_text_is_rejected() -> None:
    with pytest.raises(ExtractionError, match="scanned"):
        extract("scan.pdf", make_pdf([""]))


def test_broken_pdf() -> None:
    with pytest.raises(ExtractionError):
        extract("bad.pdf", b"%PDF-1.4 not really")


def test_docx_paragraphs_and_tables() -> None:
    data = make_docx(
        ["Policy overview", "Refunds within 30 days"], table=[["Plan", "Price"], ["Pro", "$20"]]
    )
    [page] = extract("policy.docx", data)
    assert page.number is None
    assert "Refunds within 30 days" in page.text and "Pro | $20" in page.text


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("notes.md", b"# Title\n\nSome *markdown*", "# Title\n\nSome *markdown*"),
        ("data.csv", b"name,age\nAda,36\n", "name, age\nAda, 36"),
        ("cfg.json", b'{"b":1,"a":[2]}', '{\n  "b": 1,\n  "a": [\n    2\n  ]\n}'),
        ("page.html", b"<html><script>evil()</script><h1>Hi</h1><p>There</p></html>", "Hi\nThere"),
        ("latin.txt", "caf\xe9".encode("latin-1"), "caf\xe9"),
        ("utf16.txt", "h\u00e9llo".encode("utf-16"), "h\u00e9llo"),
        ("windows.txt", "\u201cquotes\u201d".encode("cp1252"), "\u201cquotes\u201d"),
        ("bom.txt", "﻿hello".encode(), "hello"),
    ],
)
def test_text_formats(name, data, expected) -> None:
    assert extract(name, data)[0].text == expected


@pytest.mark.parametrize(
    ("name", "data"), [("x.exe", b"MZ"), ("noext", b"hi"), ("empty.txt", b"   ")]
)
def test_rejected_files(name, data) -> None:
    with pytest.raises(ExtractionError):
        extract(name, data)


# --- chunking ---------------------------------------------------------------------


def test_chunks_respect_size_overlap_and_pages() -> None:
    para = "Sentence number {} is here. "
    text = "".join(para.format(i) for i in range(200))
    chunks = chunk_pages([Page(1, text), Page(2, "Short second page.")], size=300, overlap=60)
    first_page = [c for c in chunks if c.page == 1]
    assert all(len(c.text) <= 300 for c in chunks)
    assert len(first_page) > 5 and chunks[-1].page == 2 and chunks[-1].text == "Short second page."
    # Neighbouring chunks overlap, and break at sentence ends rather than mid-word.
    assert first_page[0].text.endswith(".")
    tail = first_page[0].text[-40:]
    assert any(word in first_page[1].text for word in tail.split()[-3:])
    assert all(not c.text.startswith(("entence", "umber")) for c in chunks)


def test_short_text_is_one_chunk() -> None:
    assert [c.text for c in chunk_pages([Page(None, "Just this.")])] == ["Just this."]


def test_long_word_without_separators_still_splits() -> None:
    chunks = chunk_pages([Page(None, "x" * 2500)], size=1000, overlap=100)
    assert len(chunks) >= 3 and all(len(c.text) <= 1000 for c in chunks)


# --- search -----------------------------------------------------------------------


def test_tokenize_drops_stopwords() -> None:
    assert tokenize("What is the Refund policy, for 2026?") == ["refund", "policy", "2026"]


def test_bm25_prefers_rare_and_repeated_terms() -> None:
    cands = [
        Candidate(1, "Our refund policy allows refunds within 30 days."),
        Candidate(2, "Shipping takes 5 days. Shipping is free over $50."),
        Candidate(3, "The policy covers many things."),
    ]
    assert bm25_rank("refund policy", cands) == [1, 3]
    assert bm25_rank("shipping", cands) == [2]
    assert bm25_rank("the of", cands) == []


def test_rrf_rewards_agreement() -> None:
    assert reciprocal_rank_fusion([1, 2, 3], [3, 1, 4]) == [1, 3, 2, 4]
    assert reciprocal_rank_fusion([5], []) == [5]


def test_cosine() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0)
    assert cosine([0, 0], [1, 1]) == 0


# --- embedding engines ---------------------------------------------------------------


@respx.mock
async def test_ollama_embeddings(http) -> None:
    route = respx.post("http://ollama.test/api/embed").respond(
        json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]}
    )
    config = EmbeddingConfig("ollama", "http://ollama.test/", "nomic-embed-text")
    assert await embed(http, config, ["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert route.calls.last.request.read() == b'{"model":"nomic-embed-text","input":["a","b"]}'


@respx.mock
async def test_openai_embeddings_batched_and_ordered(http) -> None:
    def reply(request):
        import json

        inputs = json.loads(request.content)["input"]
        data = [{"index": i, "embedding": [float(len(t))]} for i, t in enumerate(inputs)]
        return httpx.Response(200, json={"data": list(reversed(data))})  # out of order on purpose

    route = respx.post("https://api.voyage.test/v1/embeddings").mock(side_effect=reply)
    config = EmbeddingConfig("openai", "https://api.voyage.test/v1", "voyage-3", api_key="vk")
    texts = ["x" * n for n in range(1, 101)]
    vectors = await embed(http, config, texts)
    assert vectors == [[float(n)] for n in range(1, 101)]
    assert len(route.calls) == 2  # 64 + 36
    assert route.calls.last.request.headers["authorization"] == "Bearer vk"


@respx.mock
async def test_embedding_errors(http) -> None:
    respx.post("http://ollama.test/api/embed").respond(404, json={"error": "model not found"})
    with pytest.raises(ProviderError, match="model not found"):
        await embed(http, EmbeddingConfig("ollama", "http://ollama.test", "nope"), ["a"])
    respx.post("http://bad.test/api/embed").respond(json={"embeddings": [[1.0]]})
    with pytest.raises(ProviderError, match="unexpected"):
        await embed(http, EmbeddingConfig("ollama", "http://bad.test", "m"), ["a", "b"])


def test_config_enabled_and_key() -> None:
    assert not EmbeddingConfig("", "", "").enabled
    c = EmbeddingConfig("ollama", "http://x", "nomic-embed-text")
    assert c.enabled and c.key == "ollama:nomic-embed-text"


def test_bm25_drops_weak_matches() -> None:
    cands = [
        Candidate(1, "Employees get 25 days of paid vacation per year. Vacation carries over."),
        Candidate(2, "Submit receipts within 30 days."),  # shares only "days"
    ]
    assert bm25_rank("How many vacation days per year?", cands) == [1]
    assert bm25_rank("How many vacation days per year?", cands, min_ratio=0) == [1, 2]


def test_close_to_best_uses_measured_margins() -> None:
    # Real nomic-embed-text similarities for "How many vacation days...?"
    scored = [(0.87, 2), (0.61, 3), (0.53, 4), (0.51, 1), (0.40, 5)]
    assert close_to_best(scored) == [2]
    # "Who is in charge of email?": a closer race keeps both near the top.
    assert close_to_best([(0.59, 4), (0.51, 1), (0.44, 2)]) == [4, 1]
    assert close_to_best([]) == []

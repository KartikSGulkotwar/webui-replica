"""Split pages into overlapping chunks that end on natural boundaries."""

from dataclasses import dataclass

from app.rag.extract import Page

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
# Prefer breaking at a paragraph, then a line, then a sentence, then a word.
SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class Chunk:
    page: int | None
    text: str


def _split(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            for sep in SEPARATORS:
                cut = window.rfind(sep)
                if cut > size // 2:  # only accept breaks that keep chunks reasonably full
                    end = start + cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
        # Don't start the overlap mid-word.
        while start < end and not text[start - 1].isspace():
            start += 1
    return chunks


def chunk_pages(
    pages: list[Page], size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[Chunk]:
    """Chunks never span pages, so each one cites a single page."""
    return [Chunk(p.number, piece) for p in pages for piece in _split(p.text, size, overlap)]

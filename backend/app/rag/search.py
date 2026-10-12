"""Hybrid retrieval: BM25 keyword ranking + vector similarity, fused with RRF."""

import math
import re
from collections import Counter
from dataclasses import dataclass

STOPWORDS = frozenset(
    "a an and are as at be but by for from has have how i if in into is it its of on or that the "
    "their there these this to was were what when where which who why will with you your".split()
)
RRF_K = 60  # standard constant for Reciprocal Rank Fusion
# Weak matches are dropped relative to the best one, so a question about one
# topic doesn't cite every document that shares a common word or sits nearby.
BM25_MIN_RATIO = 0.4  # keep keyword hits scoring at least 40% of the best
VECTOR_MARGIN = 0.10  # keep vector hits within 0.10 cosine of the best


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


@dataclass(frozen=True)
class Candidate:
    id: int
    text: str


def bm25_rank(
    query: str,
    candidates: list[Candidate],
    k1: float = 1.5,
    b: float = 0.75,
    min_ratio: float = BM25_MIN_RATIO,
) -> list[int]:
    """Candidate IDs ordered by BM25 score; chunks with no query terms, or far
    weaker than the best match, are left out."""
    terms = tokenize(query)
    if not terms or not candidates:
        return []
    docs = [Counter(tokenize(c.text)) for c in candidates]
    lengths = [sum(d.values()) for d in docs]
    avg = (sum(lengths) / len(lengths)) or 1
    n = len(docs)
    scores: list[tuple[float, int]] = []
    for cand, tf, length in zip(candidates, docs, lengths, strict=True):
        score = 0.0
        for term in set(terms):
            freq = tf.get(term, 0)
            if not freq:
                continue
            df = sum(1 for d in docs if term in d)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * length / avg))
        if score > 0:
            scores.append((score, cand.id))
    if not scores:
        return []
    best = max(score for score, _ in scores)
    kept = [(score, cid) for score, cid in scores if score >= best * min_ratio]
    return [cid for _, cid in sorted(kept, key=lambda s: (-s[0], s[1]))]


def close_to_best(scored: list[tuple[float, int]], margin: float = VECTOR_MARGIN) -> list[int]:
    """IDs from (similarity, id) pairs within `margin` of the best, best first."""
    if not scored:
        return []
    ranked = sorted(scored, key=lambda s: (-s[0], s[1]))
    best = ranked[0][0]
    return [cid for sim, cid in ranked if sim >= best - margin]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def reciprocal_rank_fusion(*rankings: list[int]) -> list[int]:
    """Merge rankings: items ranked high in any list rise; agreement adds up."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1 / (RRF_K + rank + 1)
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

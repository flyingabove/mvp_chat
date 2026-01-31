from __future__ import annotations

from pathlib import Path
import json
from typing import Any, List, Tuple

try:
    from backend.app.knowledge.build.bm25_utils import BM25_SCHEMA
except Exception:  # pragma: no cover
    BM25_SCHEMA = "bm25_v2"


def load_bm25(path: Path) -> Tuple[Any, list]:
    """
    Load a prebuilt BM25 payload.

    Required payload keys:
      - schema == BM25_SCHEMA
      - corpus_tokens: List[List[str]]
      - chunks: List[dict]
    """
    if not isinstance(path, Path):
        raise RuntimeError(f"BM25 path must be Path, got {type(path)}")

    if not path.exists():
        raise RuntimeError(f"BM25 index file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid BM25 payload at {path}: not a JSON object")

    if payload.get("schema") != BM25_SCHEMA:
        raise RuntimeError(
            f"Invalid BM25 payload at {path}: expected schema {BM25_SCHEMA!r}, got {payload.get('schema')!r}"
        )

    if "corpus_tokens" not in payload:
        raise RuntimeError(f"Invalid BM25 payload at {path}: missing 'corpus_tokens'")

    if "chunks" not in payload:
        raise RuntimeError(f"Invalid BM25 payload at {path}: missing 'chunks'")

    corpus_tokens = payload["corpus_tokens"]
    chunks = payload["chunks"]

    if not isinstance(corpus_tokens, list) or not isinstance(chunks, list):
        raise RuntimeError(f"Invalid BM25 payload at {path}: bad schema types")

    if len(corpus_tokens) != len(chunks):
        raise RuntimeError(
            f"BM25 payload mismatch at {path}: "
            f"{len(corpus_tokens)} corpus entries vs {len(chunks)} chunks"
        )

    try:
        from rank_bm25 import BM25Okapi

        bm25 = BM25Okapi(corpus_tokens)
    except Exception:
        bm25 = _FallbackBM25(corpus_tokens)
    return bm25, chunks


def search_bm25(bm25: Any, chunks: list, query: str, k: int = 5) -> List[dict]:
    if not query:
        return []

    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)

    if len(scores) != len(chunks):
        raise RuntimeError(f"BM25 runtime invariant violated: {len(scores)} scores vs {len(chunks)} chunks")

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [chunks[i] for i in top_indices]


class _FallbackBM25:
    """Minimal overlap-based scorer when rank_bm25 is unavailable."""

    def __init__(self, corpus_tokens: list[list[str]]):
        self.corpus_tokens = corpus_tokens

    def get_scores(self, query_tokens: list[str]):
        scores: List[float] = []
        qset = set(query_tokens)
        for doc in self.corpus_tokens:
            if not doc:
                scores.append(0.0)
                continue
            overlap = len(qset.intersection(doc))
            scores.append(float(overlap))
        return scores

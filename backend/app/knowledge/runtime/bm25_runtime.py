# backend/app/knowledge/runtime/bm25_runtime.py

from pathlib import Path
import json
from typing import List, Tuple
from rank_bm25 import BM25Okapi


def load_bm25(path: Path) -> Tuple[BM25Okapi, list]:
    """
    Load a prebuilt BM25 payload.

    Runtime schema invariant:
    - The payload MUST contain:
        - corpus_tokens: List[List[str]]
        - chunks: List[dict]

    Returns:
        bm25_index: BM25Okapi instance
        chunks: list of chunk dicts (canonical unit)
    """
    if not path.exists():
        raise RuntimeError(f"BM25 index file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

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

    bm25 = BM25Okapi(corpus_tokens)

    return bm25, chunks


def search_bm25(
    bm25: BM25Okapi,
    chunks: list,
    query: str,
    k: int = 5,
) -> List[dict]:
    """
    Run a BM25 search over loaded index.

    Args:
        bm25: BM25Okapi instance
        chunks: list of chunk dicts (aligned with corpus_tokens)
        query: user query
        k: number of results

    Returns:
        Top-k chunk dicts ranked by BM25 score
    """
    if not query:
        return []

    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)

    if len(scores) != len(chunks):
        raise RuntimeError(
            f"BM25 runtime invariant violated: "
            f"{len(scores)} scores vs {len(chunks)} chunks"
        )

    top_indices = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True,
    )[:k]

    return [chunks[i] for i in top_indices]

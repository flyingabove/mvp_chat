# backend/app/knowledge/common/bm25_runtime.py

from pathlib import Path
import json
from typing import List, Tuple
from rank_bm25 import BM25Okapi


def load_bm25(path: Path) -> Tuple[BM25Okapi, list]:
    """
    Load a prebuilt BM25 payload.

    Returns:
        bm25_index: BM25Okapi instance
        docs: original documents (or chunk metadata)
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    bm25 = BM25Okapi(payload["corpus_tokens"])
    docs = payload["docs"]

    return bm25, docs


def search_bm25(
    bm25: BM25Okapi,
    docs: list,
    query: str,
    k: int = 5,
) -> List[dict]:
    """
    Run a BM25 search over loaded index.

    Returns:
        Top-k document payloads (already aligned with corpus_tokens)
    """
    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)

    top_indices = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True,
    )[:k]

    return [docs[i] for i in top_indices]

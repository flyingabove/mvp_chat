from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any, Dict, List, Tuple

BM25_SCHEMA = "bm25_v2"

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣']+")


def load_chunks_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"chunks.jsonl not found: {path}")

    chunks: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def build_bm25_index(chunks: List[Dict[str, Any]], out_path: Path):
    """
    Build and persist a BM25 payload.

    Payload schema:
    {
      "schema": "bm25_v2",
      "corpus_tokens": List[List[str]],
      "chunks": List[dict]
    }
    """
    try:
        from rank_bm25 import BM25Okapi
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"rank_bm25 not available: {e}") from e

    if not chunks:
        raise RuntimeError("BM25 build failed: no chunks provided")

    corpus_tokens: List[List[str]] = []
    for c in chunks:
        text = c.get("text")
        if not isinstance(text, str):
            raise RuntimeError(f"BM25 build failed: chunk {c.get('chunk_id')} has invalid text")
        corpus_tokens.append(tokenize(text))

    payload = {
        "schema": BM25_SCHEMA,
        "corpus_tokens": corpus_tokens,
        "chunks": chunks,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    tmp.replace(out_path)

    return BM25Okapi(corpus_tokens)


def bm25_search(bm25: Any, chunks: List[Dict[str, Any]], query: str, k: int = 5) -> Tuple[List[int], List[float]]:
    q_tokens = tokenize(query)
    scores = bm25.get_scores(q_tokens)
    idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return idxs, [float(scores[i]) for i in idxs]

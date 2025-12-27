from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Tuple

import numpy as np


def load_faiss_index(index_path: Path, meta_path: Path) -> Tuple[Any, list]:
    if not index_path.exists():
        raise FileNotFoundError(f"faiss.index not found: {index_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json not found: {meta_path}")

    try:
        import faiss  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"faiss not available: {e}") from e

    index = faiss.read_index(str(index_path))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, list):
        raise RuntimeError("meta.json must be a list")
    return index, meta


def search_faiss(index: Any, metadata: list, query_embedding: Any, k: int = 5) -> List[dict]:
    try:
        import faiss  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"faiss not available: {e}") from e

    q = np.array(query_embedding, dtype="float32").reshape(1, -1)
    faiss.normalize_L2(q)
    scores, idxs = index.search(q, k)

    out: List[dict] = []
    for score, idx in zip(scores[0], idxs[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        item = dict(metadata[idx])
        item["score"] = float(score)
        out.append(item)
    return out

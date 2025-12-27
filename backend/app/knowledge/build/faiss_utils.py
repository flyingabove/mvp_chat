from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

import numpy as np


def build_faiss_index(embeddings: np.ndarray, output_path: Path):
    """
    Build and write a FAISS IndexFlatIP index to disk.
    """
    try:
        import faiss  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"faiss not available: {e}") from e

    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype("float32")

    dim = int(embeddings.shape[1])
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_path))
    return index


def faiss_search(index: Any, query_vec: Any, k: int = 5) -> Tuple[List[int], List[float]]:
    """
    Search a FAISS index (assumes inner product similarity).
    Returns (indices, scores).
    """
    try:
        import faiss  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"faiss not available: {e}") from e

    q = np.array(query_vec, dtype="float32").reshape(1, -1)
    faiss.normalize_L2(q)
    scores, idxs = index.search(q, k)
    return idxs[0].tolist(), scores[0].astype(float).tolist()

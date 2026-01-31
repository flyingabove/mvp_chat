from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

import numpy as np

from backend.app.knowledge.runtime.faiss_shim import get_faiss


def build_faiss_index(embeddings: np.ndarray, output_path: Path):
    """
    Build and write a FAISS IndexFlatIP index to disk (uses shim fallback if
    native faiss is unavailable).
    """
    faiss = get_faiss()

    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype("float32")

    dim = int(embeddings.shape[1])
    index = faiss.IndexFlatIP(dim)
    maybe_norm = faiss.normalize_L2(embeddings)
    embeddings = maybe_norm if maybe_norm is not None else embeddings
    index.add(embeddings)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_path))
    return index


def faiss_search(index: Any, query_vec: Any, k: int = 5) -> Tuple[List[int], List[float]]:
    """
    Search a FAISS index (assumes inner product similarity).
    Returns (indices, scores). Uses shim if native faiss missing.
    """
    faiss = get_faiss()

    q = np.array(query_vec, dtype="float32").reshape(1, -1)
    maybe_norm_q = faiss.normalize_L2(q)
    q = maybe_norm_q if maybe_norm_q is not None else q
    scores, idxs = index.search(q, k)
    return idxs[0].tolist(), scores[0].astype(float).tolist()

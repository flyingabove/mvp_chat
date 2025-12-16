# backend/app/knowledge/runtime/faiss_runtime.py

from pathlib import Path
from typing import List, Tuple
import json
import faiss
import numpy as np


def load_faiss_index(
    index_path: Path,
    meta_path: Path,
) -> Tuple[faiss.Index, list]:
    """
    Load FAISS index and aligned metadata.

    Returns:
        index: FAISS index
        metadata: list aligned with FAISS vectors
    """
    index = faiss.read_index(str(index_path))

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata


def search_faiss(
    index: faiss.Index,
    metadata: list,
    query_embedding: List[float],
    k: int = 5,
) -> List[dict]:
    """
    Run FAISS similarity search.

    Returns:
        Top-k metadata entries aligned to FAISS vectors.
    """
    if not isinstance(query_embedding, np.ndarray):
        query_embedding = np.array(query_embedding, dtype="float32")

    if query_embedding.ndim == 1:
        query_embedding = query_embedding.reshape(1, -1)

    scores, indices = index.search(query_embedding, k)

    results = []
    for idx in indices[0]:
        if idx == -1:
            continue
        results.append(metadata[idx])

    return results

# backend/app/knowledge/runtime/faiss_runtime.py

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Any
import json

import faiss  # type: ignore
import numpy as np


def load_faiss_index(index_path: Path, meta_path: Path) -> Tuple[faiss.Index, list]:
    if not index_path.exists():
        raise RuntimeError(f"FAISS index file not found: {index_path}")
    if not meta_path.exists():
        raise RuntimeError(f"FAISS meta file not found: {meta_path}")

    index = faiss.read_index(str(index_path))

    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    if not isinstance(meta, list):
        raise RuntimeError(f"Invalid FAISS meta schema at {meta_path}: expected list")

    return index, meta


def search_faiss(index: faiss.Index, metadata: list, query_embedding: Any, k: int = 5) -> List[dict]:
    if not isinstance(query_embedding, np.ndarray):
        query_embedding = np.array(query_embedding, dtype="float32")

    if query_embedding.ndim == 1:
        query_embedding = query_embedding.reshape(1, -1)

    scores, indices = index.search(query_embedding, k)

    results: List[dict] = []
    for idx in indices[0]:
        if idx == -1:
            continue
        if 0 <= int(idx) < len(metadata):
            results.append(metadata[int(idx)])

    return results

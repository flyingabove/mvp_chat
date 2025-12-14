# backend/app/knowledge/build/faiss_utils.py
import faiss
import numpy as np
from pathlib import Path


def build_faiss_index(embeddings: np.ndarray, output_path: Path):
    if embeddings.ndim != 2:
        raise ValueError("Embeddings must be 2D array")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype("float32"))

    faiss.write_index(index, str(output_path))
    return index

def faiss_search(index, query_vec: np.ndarray, k: int):
    scores, idxs = index.search(query_vec, k)
    return idxs[0].tolist(), scores[0].tolist()

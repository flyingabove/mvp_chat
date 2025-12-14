# backend/app/knowledge/build/faiss_utils.py
from pathlib import Path
import faiss
import numpy as np

def build_faiss_index(embeddings: np.ndarray, out_path: Path):
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine if vectors normalized
    index.add(embeddings)
    faiss.write_index(index, str(out_path))
    return index

def faiss_search(index, query_vec: np.ndarray, k: int):
    scores, idxs = index.search(query_vec, k)
    return idxs[0].tolist(), scores[0].tolist()

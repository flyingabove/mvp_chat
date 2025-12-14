# backend/app/knowledge/build/embedder.py
from typing import List
import numpy as np

_MODEL = None

def _get_model():
    global _MODEL
    if _MODEL is None:
        # Good general choice; swap later if you want multilingual (Korean+English) stronger.
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("intfloat/e5-base-v2")
    return _MODEL

def _prep(text: str) -> str:
    # e5-style: "passage:" for docs, "query:" for queries
    return text.strip()

def embed_texts(texts: List[str]) -> np.ndarray:
    m = _get_model()
    passages = [f"passage: {_prep(t)}" for t in texts]
    vecs = m.encode(passages, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    return np.asarray(vecs, dtype="float32")

def embed_query(q: str) -> np.ndarray:
    m = _get_model()
    v = m.encode([f"query: {_prep(q)}"], normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(v, dtype="float32")

def get_embedder_info():
    return {"type": "sentence-transformers", "model": "intfloat/e5-base-v2", "normalized": True}

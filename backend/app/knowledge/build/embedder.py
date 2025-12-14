# backend/app/knowledge/build/embedder.py
from typing import List
import os
import numpy as np

_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        # ---- Determinism / CI safety ----
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        try:
            import torch
            torch.set_num_threads(1)
        except Exception:
            pass

        # ---- Stable cache location (Docker / Railway safe) ----
        cache_dir = "/app/.model_cache"
        os.makedirs(cache_dir, exist_ok=True)

        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(
            "intfloat/e5-base-v2",
            cache_folder=cache_dir,
            device="cpu",  # Railway = CPU only, ensures deterministic behavior
        )

    return _MODEL


def _prep(text: str) -> str:
    # e5-style expects non-empty strings
    text = text.strip()
    return text if text else " "


def embed_texts(texts: List[str]) -> np.ndarray:
    m = _get_model()
    passages = [f"passage: {_prep(t)}" for t in texts]
    vecs = m.encode(
        passages,
        normalize_embeddings=True,
        batch_size=64,
        show_progress_bar=False,
    )
    return np.asarray(vecs, dtype="float32")


def embed_query(q: str) -> np.ndarray:
    m = _get_model()
    v = m.encode(
        [f"query: {_prep(q)}"],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(v, dtype="float32")


def get_embedder_info():
    return {
        "type": "sentence-transformers",
        "model": "intfloat/e5-base-v2",
        "normalized": True,
        "device": "cpu",
    }

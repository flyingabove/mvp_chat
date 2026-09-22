# backend/app/knowledge/build/embedder.py
from typing import List
import logging
import os
import threading
import time
import numpy as np

logger = logging.getLogger(__name__)

_MODEL = None
# Phase 1.3: `_get_model()` used to be an unguarded `if _MODEL is None` check.
# Loading this model was measured at ~15.9s, so two requests arriving during a
# cold start could BOTH enter the branch and each construct a full
# SentenceTransformer, doubling peak RSS on a memory-capped container. This lock
# makes construction single-flight: the second caller waits and reuses the first
# model. Threading (not asyncio) because callers run in executor threads too.
_MODEL_LOCK = threading.Lock()

MODEL_NAME = "intfloat/e5-base-v2"


def _resolve_cache_dir() -> str:
    """Return a writable model cache dir, preferring the Docker/Railway path.

    The hardcoded "/app/.model_cache" only exists in the container. Off-container
    (local dev, CI) `makedirs` would raise or the dir would be unwritable, and
    sentence-transformers would silently re-download the model on every cold
    start - a large part of the measured 15.9s. Fall back to a local path and say
    so, instead of failing or silently re-downloading.
    """
    candidates = [
        os.environ.get("MODEL_CACHE_DIR") or "",
        "/app/.model_cache",
        os.path.join(os.path.expanduser("~"), ".cache", "storieschat_models"),
    ]
    for cache_dir in candidates:
        if not cache_dir:
            continue
        try:
            os.makedirs(cache_dir, exist_ok=True)
            if os.access(cache_dir, os.W_OK):
                return cache_dir
        except Exception:
            continue
    # Last resort: let sentence-transformers use its own default.
    logger.warning("embedder: no writable model cache dir found; using library default")
    return ""


def _get_model():
    global _MODEL
    # Fast path: already loaded, no lock needed (module-global assignment of a
    # fully-constructed object is atomic under the GIL).
    if _MODEL is not None:
        return _MODEL

    with _MODEL_LOCK:
        # Re-check inside the lock: another thread may have loaded it while we
        # waited. Without this, the lock would serialize but still double-load.
        if _MODEL is not None:
            return _MODEL

        # ---- Determinism / CI safety ----
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        try:
            import torch
            torch.set_num_threads(1)
        except Exception:
            pass

        cache_dir = _resolve_cache_dir()

        from sentence_transformers import SentenceTransformer

        t0 = time.perf_counter()
        kwargs = {"device": "cpu"}  # Railway = CPU only, deterministic behavior
        if cache_dir:
            kwargs["cache_folder"] = cache_dir
        model = SentenceTransformer(MODEL_NAME, **kwargs)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "embedder: loaded %s in %dms (cache_dir=%s)",
            MODEL_NAME, elapsed_ms, cache_dir or "<library default>",
        )

        _MODEL = model

    return _MODEL


def is_loaded() -> bool:
    """True if the embedding model is already resident (no load triggered)."""
    return _MODEL is not None


def warm_up() -> bool:
    """Load the model and run one tiny encode so the first real request is warm.

    Blocking and CPU-bound - callers must run this in a thread, never directly
    on the event loop. Returns True on success. Never raises: a failed warm-up
    must not prevent startup, since `_get_model()` will simply retry lazily.
    """
    try:
        embed_query("warm up")
        return True
    except Exception:
        logger.exception("embedder: warm-up failed; will load lazily on first use")
        return False


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

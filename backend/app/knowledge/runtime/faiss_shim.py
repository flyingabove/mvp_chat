"""Faiss shim with pure-Python fallback for Windows/dev environments.

This module attempts to import `faiss`. If unavailable, it provides a minimal
compatible subset (IndexFlatIP, normalize_L2, write_index, read_index) backed by
NumPy. The goal is to keep local/dev tests runnable without native binaries
while preserving the real FAISS API where installed.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Tuple

import numpy as np


class _FakeIndexFlatIP:
    def __init__(self, dim: int):
        self.dim = dim
        self._vecs: np.ndarray | None = None

    def add(self, vecs: np.ndarray):
        arr = np.array(vecs, dtype="float32")
        if arr.ndim != 2 or arr.shape[1] != self.dim:
            raise ValueError("vector shape mismatch")
        arr = _fake_normalize(arr)
        if self._vecs is None:
            self._vecs = arr
        else:
            self._vecs = np.vstack([self._vecs, arr])

    def search(self, q: np.ndarray, k: int):
        if self._vecs is None or self._vecs.size == 0:
            scores = np.zeros((1, k), dtype="float32")
            idxs = -np.ones((1, k), dtype="int64")
            return scores, idxs
        q = _fake_normalize(q.astype("float32"))
        sims = np.dot(q, self._vecs.T)
        topk = min(k, self._vecs.shape[0])
        idxs = np.argpartition(-sims, topk - 1, axis=1)[:, :topk]
        # sort each row
        row_scores = np.take_along_axis(sims, idxs, axis=1)
        order = np.argsort(-row_scores, axis=1)
        idxs = np.take_along_axis(idxs, order, axis=1)
        row_scores = np.take_along_axis(row_scores, order, axis=1)
        # pad if needed
        if topk < k:
            pad = k - topk
            idxs = np.hstack([idxs, -np.ones((idxs.shape[0], pad), dtype="int64")])
            row_scores = np.hstack([row_scores, np.zeros((row_scores.shape[0], pad), dtype="float32")])
        return row_scores.astype("float32"), idxs.astype("int64")


def _fake_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
    return arr / norms


def _write_index(index: _FakeIndexFlatIP, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump({"dim": index.dim, "vecs": index._vecs}, f)


def _read_index(path: Path) -> _FakeIndexFlatIP:
    with path.open("rb") as f:
        payload = pickle.load(f)
    idx = _FakeIndexFlatIP(payload["dim"])
    idx._vecs = payload.get("vecs")
    return idx


def get_faiss():
    try:
        import faiss  # type: ignore

        return faiss
    except Exception:
        # Return a shim object exposing the subset we use.
        def _normalize(arr):
            return _fake_normalize(np.array(arr, dtype="float32"))

        FakeFaiss = type("FakeFaiss", (), {})
        FakeFaiss.IndexFlatIP = _FakeIndexFlatIP
        FakeFaiss.normalize_L2 = staticmethod(_normalize)
        FakeFaiss.write_index = staticmethod(lambda index, path: _write_index(index, Path(path)))
        FakeFaiss.read_index = staticmethod(lambda path: _read_index(Path(path)))
        return FakeFaiss()


__all__ = ["get_faiss"]

# backend/app/knowledge/build/fingerprint.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
from typing import Any, Dict


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json_hash(obj: Any) -> str:
    # stable hash: sorted keys, no whitespace
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


@dataclass(frozen=True)
class FaissConfig:
    index_type: str = "FlatIP"
    normalized: bool = True


@dataclass(frozen=True)
class Bm25Config:
    schema: str = "bm25_v2"
    tokenizer: str = "regex_v1"
    # If you later tune these, put them here and they’ll auto-invalidate caches.
    k1: float = 1.5
    b: float = 0.75


def compute_build_fingerprint(
    chunks_path: Path,
    embedder_info: Dict[str, Any],
    faiss_cfg: FaissConfig,
    bm25_cfg: Bm25Config,
) -> Dict[str, Any]:
    """
    Returns:
      {
        "chunks_hash": "...",
        "embedder_hash": "...",
        "faiss_hash": "...",
        "bm25_hash": "...",
        "fingerprint": "sha256:...."
      }
    """
    chunks_hash = sha256_file(chunks_path)
    embedder_hash = stable_json_hash(embedder_info)
    faiss_hash = stable_json_hash(asdict(faiss_cfg))
    bm25_hash = stable_json_hash(asdict(bm25_cfg))

    # One canonical fingerprint
    combined = stable_json_hash(
        {
            "chunks_hash": chunks_hash,
            "embedder_hash": embedder_hash,
            "faiss_hash": faiss_hash,
            "bm25_hash": bm25_hash,
        }
    )

    return {
        "chunks_hash": chunks_hash,
        "embedder_hash": embedder_hash,
        "faiss_hash": faiss_hash,
        "bm25_hash": bm25_hash,
        "fingerprint": f"sha256:{combined}",
    }

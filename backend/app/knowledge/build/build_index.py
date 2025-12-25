from __future__ import annotations

from pathlib import Path
import json
import time
import os
import shutil
from typing import Any, Dict, Optional

import numpy as np

from .embedder import embed_texts, embed_query, get_embedder_info
from .faiss_utils import build_faiss_index
from .bm25_utils import build_bm25_index, load_chunks_jsonl
from .tests import run_hybrid_retrieval_tests
from .fingerprint import FaissConfig, Bm25Config, compute_build_fingerprint


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

print("🔥 USING NEW build_index.py 🔥", __file__)

REQUIRED_FIELDS = {"chunk_id", "character_id", "type", "text", "confidence"}

FORCE_REBUILD = os.getenv("FORCE_REBUILD_INDEX", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR.parent

CHARACTER_DIRNAME = "1_iu"
EXPECTED_CHUNK_CHARACTER_IDS = {"iu", "1_iu"}

# If you mount a Railway Volume, set KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
CACHE_ROOT = Path(os.getenv("KNOWLEDGE_CACHE_DIR", str(KNOWLEDGE_DIR))).resolve()

CHAR_DIR = (CACHE_ROOT / "characters" / CHARACTER_DIRNAME).resolve()

CHUNKS_PATH = (
    KNOWLEDGE_DIR / "characters" / CHARACTER_DIRNAME / "chunks.jsonl"
).resolve()

# Cached artifacts (runtime requires all of these)
CACHED_CHUNKS_PATH = CHAR_DIR / "chunks.jsonl"
EMB_PATH = CHAR_DIR / "embeddings.npy"
FAISS_PATH = CHAR_DIR / "faiss.index"
BM25_PATH = CHAR_DIR / "bm25.json"
BUILD_INFO_PATH = CHAR_DIR / "build_info.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _purge_existing_cache(char_dir: Path) -> None:
    """
    Remove existing cached artifacts to guarantee a clean rebuild.
    ONLY used when FORCE_REBUILD_INDEX=1.
    """
    if char_dir.exists():
        print(f"🧹 FORCE_REBUILD_INDEX=1 → purging cache at {char_dir}")
        shutil.rmtree(char_dir)
        print(f"🧹 purge_complete exists={char_dir.exists()}")


def validate_chunks(chunks: list[dict]) -> None:
    for i, c in enumerate(chunks, start=1):
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            raise RuntimeError(
                f"chunks.jsonl line {i} missing fields: {sorted(missing)}"
            )


def load_previous_build() -> Optional[Dict[str, Any]]:
    if not BUILD_INFO_PATH.exists():
        return None
    with BUILD_INFO_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def artifacts_exist() -> bool:
    return (
        EMB_PATH.exists()
        and FAISS_PATH.exists()
        and BM25_PATH.exists()
        and CACHED_CHUNKS_PATH.exists()
    )


def should_skip(prev: Optional[Dict[str, Any]], new_fingerprint: str) -> bool:
    if FORCE_REBUILD:
        return False

    if not prev:
        return False

    old_fp = prev.get("fingerprint")
    if not old_fp:
        return False

    if old_fp != new_fingerprint:
        return False

    if not artifacts_exist():
        return False

    print("✅ Cache hit: fingerprint unchanged → skipping rebuild")
    return True


def _ensure_cached_chunks() -> None:
    if not CHUNKS_PATH.exists():
        raise RuntimeError(f"Missing chunks.jsonl at {CHUNKS_PATH}")

    if not CACHED_CHUNKS_PATH.exists():
        shutil.copy2(CHUNKS_PATH, CACHED_CHUNKS_PATH)


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    tmp.replace(path)


def _atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    np.save(tmp, arr)
    tmp_actual = tmp if tmp.suffix == ".npy" else Path(str(tmp) + ".npy")
    tmp_actual.replace(path)


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Knowledge Index Build ===")
    print("Source chunks:", CHUNKS_PATH)
    print("Cache dir:", CHAR_DIR)
    print("FORCE_REBUILD_INDEX:", "1" if FORCE_REBUILD else "0")

    if FORCE_REBUILD:
        _purge_existing_cache(CHAR_DIR)

    if not CHUNKS_PATH.exists():
        raise RuntimeError(f"Missing chunks.jsonl at {CHUNKS_PATH}")

    CHAR_DIR.mkdir(parents=True, exist_ok=True)

    # Always ensure cached chunks exist
    _ensure_cached_chunks()

    # Load + validate source chunks
    chunks = load_chunks_jsonl(CHUNKS_PATH)
    validate_chunks(chunks)

    for c in chunks:
        if c.get("character_id") not in EXPECTED_CHUNK_CHARACTER_IDS:
            raise RuntimeError(
                f"Character ID mismatch in chunk {c.get('chunk_id')}"
            )

    texts = [c["text"] for c in chunks]

    embedder_info = get_embedder_info()

    faiss_cfg = FaissConfig(index_type="FlatIP", normalized=True)
    bm25_cfg = Bm25Config(
        schema="bm25_v1",
        tokenizer="regex_v1",
        k1=1.5,
        b=0.75,
    )

    fp_info = compute_build_fingerprint(
        chunks_path=CHUNKS_PATH,
        embedder_info=embedder_info,
        faiss_cfg=faiss_cfg,
        bm25_cfg=bm25_cfg,
    )

    prev = load_previous_build()

    if should_skip(prev, fp_info["fingerprint"]):
        if not artifacts_exist():
            raise RuntimeError("Cache claimed valid but artifacts are incomplete.")
        print("ℹ️ Using existing cached artifacts")
        return

    print("🔨 Rebuilding indexes")
    start = time.time()

    # --- Embeddings + FAISS ---
    embeddings = embed_texts(texts)
    _atomic_save_npy(EMB_PATH, embeddings)

    faiss_tmp = FAISS_PATH.with_suffix(".index.tmp")
    faiss_index = build_faiss_index(embeddings, faiss_tmp)
    faiss_tmp.replace(FAISS_PATH)

    # --- BM25 ---
    bm25_tmp = BM25_PATH.with_suffix(".json.tmp")
    bm25 = build_bm25_index(chunks, bm25_tmp)
    bm25_tmp.replace(BM25_PATH)

    # --- Verify BM25 payload schema (CRITICAL) ---
    try:
        with BM25_PATH.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if "chunks" not in payload:
            raise RuntimeError(
                f"BM25 payload missing 'chunks' (keys={sorted(payload.keys())})"
            )
    except Exception as e:
        raise RuntimeError(f"BM25 payload verification failed: {e}") from e

    _ensure_cached_chunks()

    # --- Hybrid validation ---
    metrics = run_hybrid_retrieval_tests(
        chunks=chunks,
        bm25=bm25,
        faiss_index=faiss_index,
        embed_query_fn=embed_query,
        k_bm25=8,
        k_faiss=8,
        k_final=8,
    )

    print("\n=== Hybrid Retrieval Metrics ===")
    for k, v in metrics.items():
        try:
            print(f"{k}: {float(v):.3f}")
        except Exception:
            print(f"{k}: {v}")

    if metrics.get("recall", 0.0) < 0.95:
        raise RuntimeError("❌ Hybrid recall below threshold")

    build_info = {
        "character_dirname": CHARACTER_DIRNAME,
        "num_chunks": len(chunks),
        "build_time_unix": time.time(),
        "build_seconds": round(time.time() - start, 3),
        **fp_info,
        "embedder": embedder_info,
        "faiss": {
            "index_type": faiss_cfg.index_type,
            "normalized": faiss_cfg.normalized,
        },
        "bm25": {
            "schema": bm25_cfg.schema,
            "tokenizer": bm25_cfg.tokenizer,
            "k1": bm25_cfg.k1,
            "b": bm25_cfg.b,
        },
        "metrics": metrics,
    }

    _atomic_write_json(BUILD_INFO_PATH, build_info)

    if not artifacts_exist():
        raise RuntimeError("Build completed but required artifacts are missing.")

    print("✅ Knowledge index build completed successfully")


if __name__ == "__main__":
    main()

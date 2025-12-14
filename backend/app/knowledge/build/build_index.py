# backend/app/knowledge/build/build_index.py
from pathlib import Path
import json
import time
import hashlib
import os
import numpy as np

from .embedder import embed_texts, embed_query, get_embedder_info
from .faiss_utils import build_faiss_index
from .bm25_utils import build_bm25_index, load_chunks_jsonl
from .tests import run_hybrid_retrieval_tests

# --------------------
# Paths / Constants
# --------------------
BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR.parent
CHARACTER_ID = "1_iu"
CHAR_DIR = KNOWLEDGE_DIR / "characters" / CHARACTER_ID

CHUNKS_PATH = CHAR_DIR / "chunks.jsonl"
EMB_PATH = CHAR_DIR / "embeddings.npy"
FAISS_PATH = CHAR_DIR / "faiss.index"
BM25_PATH = CHAR_DIR / "bm25.json"
BUILD_INFO_PATH = CHAR_DIR / "build_info.json"

REQUIRED_FIELDS = {"chunk_id", "character_id", "type", "text", "confidence"}

# Environment toggle
FORCE_REBUILD = os.getenv("FORCE_REBUILD_INDEX", "0") == "1"

# --------------------
# Helpers
# --------------------
def validate_chunks(chunks):
    for i, c in enumerate(chunks, start=1):
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            raise ValueError(f"chunks.jsonl line {i} missing fields: {sorted(missing)}")


def compute_chunks_hash(path: Path) -> str:
    """Stable hash of chunks.jsonl for cache invalidation."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_previous_build():
    if not BUILD_INFO_PATH.exists():
        return None
    with open(BUILD_INFO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def should_skip_build(prev_build, chunks_hash, embedder_info):
    if FORCE_REBUILD:
        print("⚠️ FORCE_REBUILD_INDEX=1 → full rebuild")
        return False

    if not prev_build:
        return False

    if prev_build.get("chunks_hash") != chunks_hash:
        return False

    if prev_build.get("embedder") != embedder_info:
        return False

    required_files = [EMB_PATH, FAISS_PATH, BM25_PATH]
    if not all(p.exists() for p in required_files):
        return False

    print("✅ Cache hit: skipping index rebuild")
    return True


# --------------------
# Main
# --------------------
def main():
    print("=== Knowledge Build ===")
    print("CHAR_DIR:", CHAR_DIR)

    if not CHAR_DIR.exists():
        raise RuntimeError(f"Character directory missing: {CHAR_DIR}")
    if not CHUNKS_PATH.exists():
        raise RuntimeError(f"chunks.jsonl missing at {CHUNKS_PATH}")

    chunks = load_chunks_jsonl(CHUNKS_PATH)
    validate_chunks(chunks)

    # Basic character consistency check (non-fatal, defensive)
    for c in chunks:
        if c["character_id"] not in {"iu", CHARACTER_ID}:
            raise RuntimeError(f"Character ID mismatch in chunk: {c['chunk_id']}")

    texts = [c["text"] for c in chunks]

    chunks_hash = compute_chunks_hash(CHUNKS_PATH)
    embedder_info = get_embedder_info()
    prev_build = load_previous_build()

    if should_skip_build(prev_build, chunks_hash, embedder_info):
        print("ℹ️ Using existing FAISS/BM25 artifacts")
        return

    print("🔨 Full rebuild starting")

    # --------------------
    # Dense embeddings → FAISS
    # --------------------
    embeddings = embed_texts(texts)
    np.save(EMB_PATH, embeddings)

    faiss_index = build_faiss_index(embeddings, FAISS_PATH)

    # --------------------
    # Sparse lexical → BM25
    # --------------------
    bm25 = build_bm25_index(chunks, BM25_PATH)

    # --------------------
    # Deploy-time hybrid tests
    # --------------------
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
        print(f"{k}: {v:.3f}")

    # Recall-first gate (as requested)
    if metrics["recall"] < 0.95:
        raise RuntimeError("❌ Hybrid recall below threshold")

    # --------------------
    # Persist build metadata
    # --------------------
    build_info = {
        "character_id": CHARACTER_ID,
        "num_chunks": len(chunks),
        "chunks_hash": chunks_hash,
        "build_time_unix": time.time(),
        "embedder": embedder_info,
        "faiss": {
            "type": "FlatIP",
            "normalized": True,
        },
        "bm25": {
            "schema": "bm25_v1",
        },
        "metrics": metrics,
    }

    with open(BUILD_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(build_info, f, indent=2)

    print("✅ Hybrid build completed successfully")


if __name__ == "__main__":
    main()

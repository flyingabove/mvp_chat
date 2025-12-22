# backend/app/knowledge/build/build_index.py
from __future__ import annotations

from pathlib import Path
import json
import time
import os
import numpy as np
from typing import Any, Dict, Optional

from .embedder import embed_texts, embed_query, get_embedder_info
from .faiss_utils import build_faiss_index
from .bm25_utils import build_bm25_index, load_chunks_jsonl
from .tests import run_hybrid_retrieval_tests
from .fingerprint import FaissConfig, Bm25Config, compute_build_fingerprint
import shutil

print("Free disk:", shutil.disk_usage("/data"))

REQUIRED_FIELDS = {"chunk_id", "character_id", "type", "text", "confidence"}

FORCE_REBUILD = os.getenv("FORCE_REBUILD_INDEX", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR.parent

# You can generalize later; keeping your current behavior:
CHARACTER_DIRNAME = "1_iu"
EXPECTED_CHUNK_CHARACTER_IDS = {"iu", "1_iu"}

# If you mount a Railway Volume, set KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
CACHE_ROOT = Path(os.getenv("KNOWLEDGE_CACHE_DIR", str(KNOWLEDGE_DIR))).resolve()

CHAR_DIR = (CACHE_ROOT / "characters" / CHARACTER_DIRNAME).resolve()

CHUNKS_PATH = (KNOWLEDGE_DIR / "characters" / CHARACTER_DIRNAME / "chunks.jsonl").resolve()
# Note: chunks stay in repo; artifacts go to CACHE_ROOT if set

EMB_PATH = CHAR_DIR / "embeddings.npy"
FAISS_PATH = CHAR_DIR / "faiss.index"
BM25_PATH = CHAR_DIR / "bm25.json"
BUILD_INFO_PATH = CHAR_DIR / "build_info.json"


def validate_chunks(chunks):
    for i, c in enumerate(chunks, start=1):
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            raise ValueError(f"chunks.jsonl line {i} missing fields: {sorted(missing)}")


def load_previous_build() -> Optional[Dict[str, Any]]:
    if not BUILD_INFO_PATH.exists():
        return None
    with open(BUILD_INFO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def artifacts_exist() -> bool:
    return EMB_PATH.exists() and FAISS_PATH.exists() and BM25_PATH.exists()


def should_skip(prev_build: Optional[Dict[str, Any]], new_fingerprint: str) -> bool:
    if FORCE_REBUILD:
        print("⚠️ FORCE_REBUILD_INDEX=1 → full rebuild")
        return False
    if not prev_build:
        return False

    # Backwards compatibility with older build_info.json
    old_fp = prev_build.get("fingerprint")
    if not old_fp:
        # Fall back to old-style checks if present
        if prev_build.get("chunks_hash") and prev_build.get("embedder"):
            return (prev_build.get("chunks_hash") == prev_build.get("chunks_hash")) and artifacts_exist()
        return False

    if old_fp != new_fingerprint:
        return False

    if not artifacts_exist():
        return False

    print("✅ Cache hit: fingerprint unchanged → skipping rebuild")
    return True


def main():
    print("=== Knowledge Build ===")
    print("Repo chunks:", CHUNKS_PATH)
    print("Artifact dir:", CHAR_DIR)

    if not CHUNKS_PATH.exists():
        raise RuntimeError(f"chunks.jsonl missing at {CHUNKS_PATH}")

    CHAR_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure runtime can read chunks.jsonl from the same dir as artifacts
    dst_chunks = CHAR_DIR / "chunks.jsonl"
    if not dst_chunks.exists():
        shutil.copy2(CHUNKS_PATH, dst_chunks)


    chunks = load_chunks_jsonl(CHUNKS_PATH)
    validate_chunks(chunks)

    for c in chunks:
        if c["character_id"] not in EXPECTED_CHUNK_CHARACTER_IDS:
            raise RuntimeError(f"Character ID mismatch in chunk: {c['chunk_id']}")

    texts = [c["text"] for c in chunks]

    embedder_info = get_embedder_info()

    faiss_cfg = FaissConfig(index_type="FlatIP", normalized=True)
    bm25_cfg = Bm25Config(schema="bm25_v1", tokenizer="regex_v1", k1=1.5, b=0.75)

    fp_info = compute_build_fingerprint(
        chunks_path=CHUNKS_PATH,
        embedder_info=embedder_info,
        faiss_cfg=faiss_cfg,
        bm25_cfg=bm25_cfg,
    )

    prev = load_previous_build()

    if should_skip(prev, fp_info["fingerprint"]):
        print("ℹ️ Using existing artifacts")
        return

    print("🔨 Full rebuild starting")
    start = time.time()

    # Dense embeddings → FAISS
    embeddings = embed_texts(texts)
    np.save(EMB_PATH, embeddings)

    faiss_index = build_faiss_index(embeddings, FAISS_PATH)

    # Sparse lexical → BM25
    bm25 = build_bm25_index(chunks, BM25_PATH)

    # Tests (hybrid)
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

    if metrics["recall"] < 0.95:
        raise RuntimeError("❌ Hybrid recall below threshold")

    build_info = {
        "character_dirname": CHARACTER_DIRNAME,
        "num_chunks": len(chunks),
        "build_time_unix": time.time(),
        "build_seconds": round(time.time() - start, 3),
        # hashes/fingerprint
        **fp_info,
        # configs that influence fingerprint
        "embedder": embedder_info,
        "faiss": {"index_type": faiss_cfg.index_type, "normalized": faiss_cfg.normalized},
        "bm25": {"schema": bm25_cfg.schema, "tokenizer": bm25_cfg.tokenizer, "k1": bm25_cfg.k1, "b": bm25_cfg.b},
        "metrics": metrics,
    }

    with open(BUILD_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(build_info, f, indent=2)

    print("✅ Hybrid build completed successfully")


if __name__ == "__main__":
    main()

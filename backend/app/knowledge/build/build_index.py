# backend/app/knowledge/build/build_index.py
from pathlib import Path
import json, time
import numpy as np

from embedder import embed_texts, embed_query, get_embedder_info
from faiss_utils import build_faiss_index
from bm25_utils import build_bm25_index, load_chunks_jsonl
from tests import run_hybrid_retrieval_tests

# ✅ FIX: resolve character directory relative to THIS file
BASE_DIR = Path(__file__).resolve().parent            # /app/backend/app/knowledge/build
CHAR_DIR = BASE_DIR.parent / "characters" / "1_iu"   # /app/backend/app/knowledge/characters/1_iu

REQUIRED_FIELDS = {"chunk_id", "character_id", "type", "text", "confidence"}

def validate_chunks(chunks):
    for i, c in enumerate(chunks, start=1):
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            raise ValueError(f"chunks.jsonl line {i} missing fields: {sorted(missing)}")

def main():
    chunks_path = CHAR_DIR / "chunks.jsonl"
    chunks = load_chunks_jsonl(chunks_path)
    validate_chunks(chunks)

    texts = [c["text"] for c in chunks]

    # Dense embeddings → FAISS
    embeddings = embed_texts(texts)  # (N, D)
    emb_path = CHAR_DIR / "embeddings.npy"
    np.save(emb_path, embeddings)

    faiss_path = CHAR_DIR / "faiss.index"
    faiss_index = build_faiss_index(embeddings, faiss_path)

    # Sparse lexical → BM25
    bm25_path = CHAR_DIR / "bm25.json"
    bm25 = build_bm25_index(chunks, bm25_path)

    # Deploy-time tests (hybrid)
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

    # Gate on recall (recall > precision)
    if metrics["recall"] < 0.95:
        raise RuntimeError("❌ Hybrid recall below threshold")

    build_info = {
        "character_id": "iu",
        "num_chunks": len(chunks),
        "build_time_unix": time.time(),
        "embedder": get_embedder_info(),
        "metrics": metrics,
    }
    with open(CHAR_DIR / "build_info.json", "w", encoding="utf-8") as f:
        json.dump(build_info, f, indent=2)

    print("✅ Hybrid build completed successfully")

if __name__ == "__main__":
    main()

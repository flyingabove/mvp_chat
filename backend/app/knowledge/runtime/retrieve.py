# backend/app/knowledge/runtime/retrieve.py

from __future__ import annotations

from typing import Tuple, List, Dict, Any

from backend.app.knowledge.runtime.index_store import get_indexes


def retrieve_knowledge(
    query: str,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hybrid BM25 + FAISS retrieval.

    Returns:
      retrieved_chunks: List[chunk dict]
      debug_info: dict of indices/scores
    """
    if not query:
        return [], {"error": "empty_query"}

    indexes = get_indexes()
    chunks = indexes["chunks"]
    bm25 = indexes["bm25"]
    faiss_index = indexes["faiss"]

    # Lazy imports (avoid heavy import at module load / tests)
    from backend.app.knowledge.build.embedder import embed_query
    from backend.app.knowledge.build.faiss_utils import faiss_search
    from backend.app.knowledge.build.hybrid import hybrid_retrieve

    # --- BM25 scores / top-k indices ---
    q_tokens = query.lower().split()
    scores = bm25.get_scores(q_tokens)

    bm25_idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k_bm25]
    bm25_scores = [float(scores[i]) for i in bm25_idxs]

    # --- FAISS top-k indices ---
    qv = embed_query(query)
    faiss_idxs, faiss_scores = faiss_search(faiss_index, qv, k=k_faiss)

    # --- Fuse ---
    fused_idxs = hybrid_retrieve(bm25_idxs, faiss_idxs, top_k=k_final)

    retrieved_chunks = [chunks[i] for i in fused_idxs if 0 <= i < len(chunks)]

    return retrieved_chunks, {
        "bm25_idxs": bm25_idxs,
        "bm25_scores": bm25_scores,
        "faiss_idxs": faiss_idxs,
        "faiss_scores": faiss_scores,
        "fused_idxs": fused_idxs,
    }

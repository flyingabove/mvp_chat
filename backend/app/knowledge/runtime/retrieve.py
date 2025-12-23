# app/knowledge/runtime/retrieve.py

"""
Runtime knowledge retrieval wrapper.

This module is the ONLY runtime-facing entrypoint for knowledge retrieval.

Design goals:
- Zero heavy work at import time
- Lazy, thread-safe index loading
- Compatible with hash-based rebuild logic
- Safe for tests and deploys
"""

from typing import Tuple, List, Dict, Any


# ---------------------------------------------------------------------------
# RUNTIME RETRIEVAL API
# ---------------------------------------------------------------------------
def retrieve_knowledge(
    query: str,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Perform hybrid BM25 + FAISS retrieval.

    Returns:
        retrieved_chunks: List[chunk dicts]
        debug_info: metadata useful for logging/inspection
    """
    # Lazy load indexes (no import-time work)
    from app.knowledge.runtime.index_store import get_indexes

    try:
        indexes = get_indexes()
    except Exception as e:
        # Loud failure — better than silent hallucination
        return [], {"error": f"index_load_failed: {e}"}

    if not indexes:
        return [], {"error": "indexes_empty"}

    try:
        chunks = indexes["chunks"]
        bm25 = indexes["bm25"]
        faiss_index = indexes["faiss"]
        search_bm25_fn = indexes["search_bm25"]

        # Build-time utilities imported lazily
        from app.knowledge.build.embedder import embed_query
        from app.knowledge.build.faiss_utils import faiss_search
        from app.knowledge.build.hybrid import hybrid_retrieve

        bm25_idxs, bm25_scores = search_bm25_fn(bm25, query, k=k_bm25)

        qv = embed_query(query)
        faiss_idxs, faiss_scores = faiss_search(faiss_index, qv, k=k_faiss)

        fused_idxs = hybrid_retrieve(bm25_idxs, faiss_idxs, top_k=k_final)

        # IMPORTANT: pass through ORIGINAL chunk objects
        retrieved_chunks = [
            chunks[i] for i in fused_idxs if 0 <= i < len(chunks)
        ]

        return retrieved_chunks, {
            "bm25_idxs": bm25_idxs,
            "bm25_scores": bm25_scores,
            "faiss_idxs": faiss_idxs,
            "faiss_scores": faiss_scores,
            "fused_idxs": fused_idxs,
        }

    except Exception as e:
        return [], {"error": f"retrieval_failed: {e}"}

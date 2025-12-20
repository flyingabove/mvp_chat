# app/knowledge/runtime/retrieve.py

"""
Runtime knowledge retrieval wrapper.

This module is the ONLY runtime-facing entrypoint for knowledge retrieval.
It intentionally wraps build-time utilities (BM25, FAISS, embedding) behind
a stable runtime API so that api/chat.py never imports build/* directly.

Behavior is identical to the previous inline implementation in chat.py.
"""

from typing import Tuple, List, Dict, Any
import json

from backend.app.knowledge.runtime.load_indexes import load_character_indexes


# ---------------------------------------------------------------------------
# SAFE INDEX LOADING (no boot crash)
# ---------------------------------------------------------------------------
try:
    INDEXES = load_character_indexes()
except Exception as e:
    INDEXES = None
    print(json.dumps({
        "kind": "index_load_failed",
        "error": str(e)
    }))


# ---------------------------------------------------------------------------
# RUNTIME RETRIEVAL API
# ---------------------------------------------------------------------------
def retrieve_knowledge(
    query: str,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Perform hybrid BM25 + FAISS retrieval for runtime use.

    Returns:
        retrieved_chunks: List[dict]
        debug_info: Dict[str, Any]
    """
    if not INDEXES:
        return [], {"error": "indexes not loaded"}

    try:
        chunks = INDEXES["chunks"]
        chunk_ids = INDEXES["chunk_ids"]
        bm25 = INDEXES["bm25"]
        faiss_index = INDEXES["faiss"]
        search_bm25_fn = INDEXES["search_bm25"]

        # Lazy imports of build utilities (runtime-safe boundary)
        from backend.app.knowledge.build.embedder import embed_query
        from backend.app.knowledge.build.faiss_utils import faiss_search
        from backend.app.knowledge.build.hybrid import hybrid_retrieve

        bm25_idxs, bm25_scores = search_bm25_fn(bm25, query, k=k_bm25)

        qv = embed_query(query)
        faiss_idxs, faiss_scores = faiss_search(faiss_index, qv, k=k_faiss)

        fused = hybrid_retrieve(bm25_idxs, faiss_idxs, top_k=k_final)

        out = []
        for i in fused:
            if 0 <= i < len(chunks):
                out.append({
                    "i": i,
                    "chunk_id": chunk_ids[i],
                    "type": chunks[i].get("type", ""),
                    "text": chunks[i].get("text", ""),
                    "confidence": chunks[i].get("confidence", ""),
                })

        return out, {
            "bm25_idxs": bm25_idxs,
            "bm25_scores": bm25_scores,
            "faiss_idxs": faiss_idxs,
            "faiss_scores": faiss_scores,
            "fused_idxs": fused,
        }

    except Exception as e:
        return [], {"error": str(e)}

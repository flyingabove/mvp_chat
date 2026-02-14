from __future__ import annotations

from typing import Tuple, List, Dict, Any, Optional

from backend.app.knowledge.runtime.index_service import IndexService


def retrieve_knowledge(
    query: str,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8,
    namespace: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hybrid BM25 + FAISS retrieval.

    Returns:
      retrieved_chunks: List[chunk dict]
      debug_info: dict of indices/scores
    """
    if not query:
        return [], {"error": "empty_query"}

    bundle = IndexService.get()
    chunks = bundle.chunks
    bm25 = getattr(bundle, "bm25", None)
    faiss_index = getattr(bundle, "faiss_index", None)

    # If full artifacts are available, use hybrid retrieval.
    if bm25 is not None and faiss_index is not None:
        # Lazy imports (avoid heavy import at module load / tests)
        from backend.app.knowledge.build.embedder import embed_query
        from backend.app.knowledge.build.faiss_utils import faiss_search
        from backend.app.knowledge.build.hybrid import hybrid_retrieve

        q_tokens = query.lower().split()
        scores = bm25.get_scores(q_tokens)

        sorted_idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        def _filter_by_namespace(idxs: List[int], limit: int) -> List[int]:
            out: List[int] = []
            for i in idxs:
                if i < 0 or i >= len(chunks):
                    continue
                if namespace and (chunks[i].get("namespace") or chunks[i].get("ns")) != namespace:
                    continue
                out.append(i)
                if len(out) >= limit:
                    break
            return out

        bm25_idxs = _filter_by_namespace(sorted_idxs, k_bm25)
        bm25_scores = [float(scores[i]) for i in bm25_idxs]

        qv = embed_query(query)
        search_k = min(len(chunks), max(k_faiss, k_final, 16))
        faiss_idxs, faiss_scores = faiss_search(faiss_index, qv, k=search_k)

        faiss_filtered = _filter_by_namespace(faiss_idxs, k_faiss)
        faiss_scores_filtered: List[float] = []
        for idx, score in zip(faiss_idxs, faiss_scores):
            if idx in faiss_filtered:
                faiss_scores_filtered.append(float(score))

        fused_idxs = hybrid_retrieve(bm25_idxs, faiss_filtered, top_k=k_final)
        retrieved_chunks = [chunks[i] for i in fused_idxs if 0 <= i < len(chunks)]

        return retrieved_chunks, {
            "bm25_idxs": bm25_idxs,
            "bm25_scores": bm25_scores,
            "faiss_idxs": faiss_filtered,
            "faiss_scores": faiss_scores_filtered,
            "fused_idxs": fused_idxs,
            "mode": "hybrid",
            "namespace": namespace,
        }

    # Fallback: simple keyword scoring over chunk text.
    q = query.lower().strip()
    q_terms = [t for t in q.split() if t]

    def _score(text: str) -> int:
        t = (text or "").lower()
        s = 0
        for term in q_terms:
            if term in t:
                s += 1
        # Boost discography-like items for song queries.
        if any(tk in q for tk in ("song", "songs", "sing", "sang", "discography")):
            if "song" in t or "title" in t:
                s += 1
        return s

    scored = [(i, _score(c.get("text", ""))) for i, c in enumerate(chunks)]
    scored.sort(key=lambda x: x[1], reverse=True)

    top: List[int] = []
    for i, s in scored:
        if s <= 0:
            continue
        if namespace and (chunks[i].get("namespace") or chunks[i].get("ns")) != namespace:
            continue
        top.append(i)
        if len(top) >= k_final:
            break
    if not top:
        # As a last resort, return the first few chunks to avoid empty retrieval.
        fallback_idxs = list(range(min(k_final, len(chunks))))
        top = [i for i in fallback_idxs if not namespace or (chunks[i].get("namespace") or chunks[i].get("ns")) == namespace]
    retrieved_chunks = [chunks[i] for i in top]

    return retrieved_chunks, {
        "mode": "fallback",
        "top_idxs": top,
        "namespace": namespace,
    }

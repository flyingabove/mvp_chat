from __future__ import annotations

from typing import TYPE_CHECKING, Tuple, List, Dict, Any, Optional

from backend.app.knowledge.runtime.index_service import IndexService

if TYPE_CHECKING:
    from backend.app.knowledge.runtime.session_chunk_store import SessionChunkStore


def retrieve_knowledge(
    query: str,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8,
    namespace: Optional[str] = None,
    session_store: Optional["SessionChunkStore"] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hybrid BM25 + FAISS retrieval, optionally supplemented by session-level chunks.

    session_store: an optional SessionChunkStore holding facts extracted from
      prior dialogue turns. Its results are merged with the main retrieval
      results, deduplicated by chunk_id, up to k_final total chunks.

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
        # Use a set for O(1) membership checks instead of O(n) list scan.
        faiss_filtered_set = set(faiss_filtered)
        for idx, score in zip(faiss_idxs, faiss_scores):
            if idx in faiss_filtered_set:
                faiss_scores_filtered.append(float(score))

        fused_idxs = hybrid_retrieve(bm25_idxs, faiss_filtered, top_k=k_final)
        retrieved_chunks = [chunks[i] for i in fused_idxs if 0 <= i < len(chunks)]

        session_hits, session_count = _merge_session_chunks(
            retrieved_chunks, session_store, query, k_final
        )

        return session_hits, {
            "bm25_idxs": bm25_idxs,
            "bm25_scores": bm25_scores,
            "faiss_idxs": faiss_filtered,
            "faiss_scores": faiss_scores_filtered,
            "fused_idxs": fused_idxs,
            "mode": "hybrid",
            "namespace": namespace,
            "session_chunks_added": session_count,
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

    session_hits, session_count = _merge_session_chunks(
        retrieved_chunks, session_store, query, k_final
    )

    return session_hits, {
        "mode": "fallback",
        "top_idxs": top,
        "namespace": namespace,
        "session_chunks_added": session_count,
    }


def _merge_session_chunks(
    main_results: List[Dict[str, Any]],
    session_store: Optional["SessionChunkStore"],
    query: str,
    k_final: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Merge session-level chunks into main retrieval results.

    Session chunks fill remaining slots up to k_final, deduplicated by chunk_id.
    Returns (merged_list, number_of_session_chunks_added).
    """
    if not session_store:
        return main_results, 0

    seen_ids = {c.get("chunk_id") for c in main_results}
    remaining = max(0, k_final - len(main_results))
    if remaining == 0:
        return main_results, 0

    session_hits = session_store.query(query, top_k=remaining + 4)
    added = [c for c in session_hits if c.get("chunk_id") not in seen_ids][:remaining]
    return main_results + added, len(added)

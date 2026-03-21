# backend/app/knowledge/build/hybrid.py
from typing import List, Dict

def rrf_fuse(ranked_lists: List[List[int]], k: int = 60) -> Dict[int, float]:
    # RRF score: sum(1 / (k + rank))
    scores = {}
    for lst in ranked_lists:
        for rank, idx in enumerate(lst, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return scores

def hybrid_retrieve(
    bm25_idxs: List[int],
    faiss_idxs: List[int],
    top_k: int = 8,
) -> List[int]:
    scores = rrf_fuse([bm25_idxs, faiss_idxs], k=60)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in ranked[:top_k]]

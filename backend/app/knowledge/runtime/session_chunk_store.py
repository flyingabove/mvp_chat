"""
Session-level in-memory knowledge chunk store.

Holds facts extracted from user/AI dialogue during a single game session.
Chunk IDs encode their source:
  usr-{msg_id}-{n}  — extracted from a user message
  ai-{msg_id}-{n}   — extracted from an AI message
  game-{id}         — game-canon (not stored here; handled by main index)

Used by retrieve_knowledge() to supplement FAISS/BM25 game-canon results.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣']+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


class SessionChunkStore:
    """Per-session in-memory BM25 chunk store."""

    def __init__(self) -> None:
        self._chunks: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Append one or more chunk dicts to the store."""
        for c in chunks:
            if c.get("chunk_id") and c.get("text"):
                self._chunks.append(c)

    def query(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """BM25-score all stored chunks against query, return top-k by score.

        Rebuilds BM25Okapi from the current chunk list. Cheap for typical
        session sizes (<200 chunks). Returns [] if store is empty or
        rank_bm25 is unavailable.
        """
        if not self._chunks:
            return []
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
        except ImportError:
            return self._keyword_fallback(query, top_k)

        corpus = [_tokenize(c["text"]) for c in self._chunks]
        # Avoid empty-corpus crash (BM25Okapi requires ≥1 doc)
        if not any(corpus):
            return []

        bm25 = BM25Okapi(corpus)
        q_tokens = _tokenize(query)
        scores = bm25.get_scores(q_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i] for i in ranked[:top_k] if scores[i] > 0]

    def __len__(self) -> int:
        return len(self._chunks)

    def all_chunks(self) -> List[Dict[str, Any]]:
        return list(self._chunks)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _keyword_fallback(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Simple keyword overlap scoring when rank_bm25 is unavailable."""
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return self._chunks[:top_k]
        scored = [
            (len(q_tokens & set(_tokenize(c["text"]))), i)
            for i, c in enumerate(self._chunks)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._chunks[i] for score, i in scored[:top_k] if score > 0]

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Any

import faiss  # type: ignore
from rank_bm25 import BM25Okapi


@dataclass(frozen=True)
class CharacterIndexBundle:
    """
    Canonical, typed container for all retrieval artifacts
    for a single character.

    This is the ONLY object runtime code should depend on.
    """

    character_id: str
    artifact_dir: Path

    # Canonical data
    chunks: List[dict]            # will become Chunk objects later
    chunk_ids: List[str]

    # Indexes
    bm25: BM25Okapi
    faiss_index: faiss.Index

    def __post_init__(self) -> None:
        # Defensive invariants (fail fast, loud)
        if not self.chunks:
            raise RuntimeError("CharacterIndexBundle initialized with empty chunks")

        if len(self.chunks) != len(self.chunk_ids):
            raise RuntimeError(
                "chunks and chunk_ids length mismatch "
                f"({len(self.chunks)} vs {len(self.chunk_ids)})"
            )

        if any(not cid for cid in self.chunk_ids):
            raise RuntimeError("One or more chunks missing chunk_id")

        if not self.artifact_dir.exists():
            raise RuntimeError(f"artifact_dir does not exist: {self.artifact_dir}")

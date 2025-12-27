from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Any


@dataclass(frozen=True)
class CharacterIndexBundle:
    character_id: str
    artifact_dir: Path
    chunks: List[dict]
    chunk_ids: List[str]

    # Typed as Any to avoid importing rank_bm25/faiss at module import time.
    bm25: Any
    faiss_index: Any

# backend/app/knowledge/runtime/load_indexes.py

from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
from typing import Dict, Any, List, Tuple

import faiss  # type: ignore

from backend.app.knowledge.runtime.bm25_runtime import load_bm25


REQUIRED_FILES = ("faiss.index", "bm25.json", "chunks.jsonl")


def _load_chunks_jsonl(path: Path) -> List[dict]:
    chunks: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
    return chunks


def _has_required(d: Path) -> bool:
    if not d.exists():                      # <-- defensive, minimal
        return False
    return all((d / name).exists() for name in REQUIRED_FILES)


def _copy_tree(src: Path, dst: Path, filenames: Tuple[str, ...]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        s = src / name
        t = dst / name
        if s.exists() and not t.exists():
            shutil.copy2(s, t)


def load_character_indexes(character_id: str = "1_iu") -> Dict[str, Any]:
    """
    Load retrieval artifacts for a character.

    Resolution order:
    1) Persistent cache directory (Railway volume) if complete
    2) Image-bundled artifacts inside container (repo path)

    Fails loudly if artifacts are missing or invalid.
    """

    # Image-bundled knowledge dir: .../app/knowledge
    image_knowledge_dir = Path(__file__).resolve().parents[1]
    image_char_dir = image_knowledge_dir / "characters" / character_id

    # Persistent cache root
    persist_root_str = (
        os.getenv("KNOWLEDGE_CACHE_DIR")
        or os.getenv("KNOWLEDGE_PERSIST_ROOT")
        or "/data/knowledge_cache"
    )
    persist_root = Path(persist_root_str).resolve()
    persist_char_dir = persist_root / "characters" / character_id

    use_dir: Path | None = None

    if _has_required(persist_char_dir):
        use_dir = persist_char_dir
    elif _has_required(image_char_dir):
        use_dir = image_char_dir

        # Best-effort copy to cache for future boots
        if persist_root.exists():
            try:
                _copy_tree(image_char_dir, persist_char_dir, REQUIRED_FILES)
            except Exception:
                pass
    else:
        missing_persist = [
            name for name in REQUIRED_FILES
            if not (persist_char_dir / name).exists()
        ]
        missing_image = [
            name for name in REQUIRED_FILES
            if not (image_char_dir / name).exists()
        ]
        raise RuntimeError(
            "Could not locate required knowledge artifacts. "
            f"Checked persistent: {persist_char_dir} "
            f"Checked image: {image_char_dir} "
            f"Missing at least: {', '.join(sorted(set(missing_persist + missing_image)))}"
        )

    # --- Load artifacts ---
    chunks_path = use_dir / "chunks.jsonl"
    bm25_path = use_dir / "bm25.json"
    faiss_path = use_dir / "faiss.index"

    chunks = _load_chunks_jsonl(chunks_path)

    try:
        print("DEBUG bm25.json contents:", bm25_path.read_text()[:500])
        bm25, _ = load_bm25(bm25_path)      # <-- Path preserved
    except Exception as e:
        # Normalize failure mode so tests & runtime get RuntimeError
        raise RuntimeError(f"Failed to load BM25 index at {bm25_path}: {e}") from e

    faiss_index = faiss.read_index(str(faiss_path))

    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    return {
        "chunks": chunks,
        "chunk_ids": chunk_ids,
        "bm25": bm25,
        "faiss": faiss_index,
        "artifact_dir": str(use_dir),
    }

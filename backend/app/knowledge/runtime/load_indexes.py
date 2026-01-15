from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
from typing import List, Tuple

from backend.app.knowledge.contracts.index_bundle import CharacterIndexBundle
from backend.app.knowledge.runtime.bm25_runtime import load_bm25

REQUIRED_FILES = ("chunks.jsonl",)


def _load_chunks_jsonl(path: Path) -> List[dict]:
    chunks: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def _has_required(d: Path) -> bool:
    if not d.exists():
        return False
    return all((d / name).exists() for name in REQUIRED_FILES)


def _copy_tree(src: Path, dst: Path, filenames: Tuple[str, ...]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        s = src / name
        t = dst / name
        if s.exists() and not t.exists():
            shutil.copy2(s, t)


def load_character_indexes(character_id: str) -> CharacterIndexBundle:
    """
    Load retrieval artifacts for a character and return a strongly-typed bundle.

    Resolution order:
      1) Persistent cache directory (Railway volume)
      2) Image-bundled artifacts inside container

    Fails loudly if artifacts are missing or invalid.
    """

    # Image-bundled knowledge dir: backend/app/knowledge
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

        # Best-effort copy to persistent cache
        if persist_root.exists():
            try:
                _copy_tree(image_char_dir, persist_char_dir, REQUIRED_FILES)
            except Exception:
                pass
    else:
        missing = sorted(
            set(
                name
                for name in REQUIRED_FILES
                if not (persist_char_dir / name).exists()
                and not (image_char_dir / name).exists()
            )
        )
        raise RuntimeError(
            "Could not locate required knowledge artifacts. "
            f"Checked persistent: {persist_char_dir} "
            f"Checked image: {image_char_dir} "
            f"Missing at least: {', '.join(missing)}"
        )

    assert use_dir is not None

    chunks_path = use_dir / "chunks.jsonl"
    bm25_path = use_dir / "bm25.json"
    faiss_path = use_dir / "faiss.index"

    chunks = _load_chunks_jsonl(chunks_path)

    bm25 = None
    faiss_index = None

    if bm25_path.exists():
        try:
            bm25, _ = load_bm25(bm25_path)
        except Exception as e:
            # Leave bm25 None; retrieval will fallback to simple search.
            bm25 = None

    if faiss_path.exists():
        try:
            import faiss  # type: ignore
            faiss_index = faiss.read_index(str(faiss_path))
        except Exception:
            faiss_index = None
    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    return CharacterIndexBundle(
        character_id=character_id,
        artifact_dir=use_dir,
        chunks=chunks,
        chunk_ids=chunk_ids,
        bm25=bm25,
        faiss_index=faiss_index,
    )

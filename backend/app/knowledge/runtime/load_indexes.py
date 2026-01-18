from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
from typing import List, Tuple

from backend.app.knowledge.contracts.index_bundle import CharacterIndexBundle
from backend.app.knowledge.runtime.bm25_runtime import load_bm25

# Runtime requires built artifacts (not just source chunks).
# These are produced by backend.app.knowledge.build.build_index into KNOWLEDGE_CACHE_DIR.
REQUIRED_FILES = (
    "chunks.jsonl",
    "bm25.json",
    "faiss.index",
    "embeddings.npy",
    "build_info.json",
)


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




def _try_autobuild_indexes(character_id: str, persist_root: Path, persist_char_dir: Path) -> None:
    """Attempt to build missing knowledge artifacts into the persistent cache.

    Safety rules:
    - If KNOWLEDGE_PERSIST_ROOT is explicitly set, we do NOT autobuild (tests expect hard failure).
    - Only autobuild when KNOWLEDGE_CACHE_DIR points at /data (integration invariant).
    """
    if os.getenv("KNOWLEDGE_PERSIST_ROOT"):
        return
    cache_dir = os.getenv("KNOWLEDGE_CACHE_DIR", "")
    if not cache_dir.startswith("/data"):
        return

    old_cache = os.getenv("KNOWLEDGE_CACHE_DIR")
    old_force = os.getenv("FORCE_REBUILD_INDEX")
    os.environ["KNOWLEDGE_CACHE_DIR"] = str(persist_root)
    os.environ["FORCE_REBUILD_INDEX"] = "1"
    try:
        from backend.app.knowledge.build import build_index
        build_index.main()
    finally:
        if old_cache is None:
            os.environ.pop("KNOWLEDGE_CACHE_DIR", None)
        else:
            os.environ["KNOWLEDGE_CACHE_DIR"] = old_cache
        if old_force is None:
            os.environ.pop("FORCE_REBUILD_INDEX", None)
        else:
            os.environ["FORCE_REBUILD_INDEX"] = old_force

    if not _has_required(persist_char_dir):
        missing = [n for n in REQUIRED_FILES if not (persist_char_dir / n).exists()]
        raise RuntimeError(
            "Autobuild attempted but required knowledge artifacts are still missing: "
            + ", ".join(missing)
        )

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
        # In-repo image artifacts are only valid if they include the built indexes.
        use_dir = image_char_dir

        # Best-effort copy to persistent cache
        if persist_root.exists():
            try:
                _copy_tree(image_char_dir, persist_char_dir, REQUIRED_FILES)
            except Exception:
                pass
    else:
        # If we're running in the real deployment-style layout (/data cache),
        # attempt to build the missing artifacts into the persistent cache.
        # (Integration tests require the cache to live under /data.)
        if str(persist_root).startswith("/data"):
            try:
                from backend.app.knowledge.build.build_index import main as build_main

                build_main()
            except Exception:
                # Fall through to explicit error below.
                pass

            if _has_required(persist_char_dir):
                use_dir = persist_char_dir

    if use_dir is None:
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

    # These must exist (enforced by REQUIRED_FILES / _has_required). Load loudly.
    try:
        bm25, _ = load_bm25(bm25_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load BM25 index at {bm25_path}: {e}") from e

    try:
        import faiss  # type: ignore

        faiss_index = faiss.read_index(str(faiss_path))
    except Exception as e:
        raise RuntimeError(f"Failed to load FAISS index at {faiss_path}: {e}") from e
    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    return CharacterIndexBundle(
        character_id=character_id,
        artifact_dir=use_dir,
        chunks=chunks,
        chunk_ids=chunk_ids,
        bm25=bm25,
        faiss_index=faiss_index,
    )

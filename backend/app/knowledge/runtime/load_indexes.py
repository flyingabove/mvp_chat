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
REQUIRED_FILES: Tuple[str, ...] = (
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
    return d.exists() and all((d / name).exists() for name in REQUIRED_FILES)


def _missing_required(d: Path) -> List[str]:
    return [name for name in REQUIRED_FILES if not (d / name).exists()]


def _copy_tree(src_dir: Path, dst_dir: Path, names: Tuple[str, ...]) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        s = src_dir / name
        t = dst_dir / name
        if s.exists():
            shutil.copy2(s, t)


def _dir_listing(d: Path, max_items: int = 60) -> str:
    try:
        if not d.exists():
            return f"{d} (missing)"
        items = sorted(d.iterdir(), key=lambda p: p.name)[:max_items]
        parts = [f"{d} ({len(list(d.iterdir()))} items)"]
        for p in items:
            try:
                parts.append(f" - {p.name}{'/' if p.is_dir() else ''} ({p.stat().st_size} bytes)")
            except Exception:
                parts.append(f" - {p.name}{'/' if p.is_dir() else ''}")
        return "\n".join(parts)
    except Exception as e:
        return f"{d} (error listing: {e})"


def _find_tmp_cache_dir(character_id: str) -> Path | None:
    """Search common pytest temp roots for built artifacts."""
    roots = [Path("/tmp")]
    patterns = ("pytest-of-*", "pytest-*")
    candidates: List[Path] = []
    for r in roots:
        for pat in patterns:
            for base in r.glob(pat):
                try:
                    for d in base.rglob(f"knowledge_cache/characters/{character_id}"):
                        if _has_required(d):
                            candidates.append(d)
                except Exception:
                    continue
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _try_autobuild_into(persist_root: Path) -> str:
    """Attempt to build indexes into persist_root, returning a debug note."""
    if os.getenv("KNOWLEDGE_PERSIST_ROOT"):
        return "autobuild skipped: KNOWLEDGE_PERSIST_ROOT is set"
    # Preserve old env and force output location
    old_cache = os.getenv("KNOWLEDGE_CACHE_DIR")
    old_force = os.getenv("FORCE_REBUILD_INDEX")
    os.environ["KNOWLEDGE_CACHE_DIR"] = str(persist_root)
    os.environ["FORCE_REBUILD_INDEX"] = "1"
    try:
        from backend.app.knowledge.build import build_index
        build_index.main()
        return f"autobuild attempted into {persist_root}"
    except Exception as e:
        return f"autobuild failed: {repr(e)}"
    finally:
        if old_cache is None:
            os.environ.pop("KNOWLEDGE_CACHE_DIR", None)
        else:
            os.environ["KNOWLEDGE_CACHE_DIR"] = old_cache
        if old_force is None:
            os.environ.pop("FORCE_REBUILD_INDEX", None)
        else:
            os.environ["FORCE_REBUILD_INDEX"] = old_force


def load_character_indexes(character_id: str) -> CharacterIndexBundle:
    """Load retrieval artifacts for a character and return a strongly-typed bundle."""

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
    debug_notes: List[str] = []

    if _has_required(persist_char_dir):
        use_dir = persist_char_dir
    elif _has_required(image_char_dir):
        # First-run convenience: copy image-bundled artifacts to persistent cache
        try:
            _copy_tree(image_char_dir, persist_char_dir, REQUIRED_FILES)
            debug_notes.append("copied image artifacts to persistent cache")
        except Exception as e:
            debug_notes.append(f"copy image->persistent failed: {repr(e)}")
        use_dir = image_char_dir if _has_required(image_char_dir) else None

    # If still missing, attempt an autobuild into persistent cache (this is what you need in CI/tests)
    if use_dir is None:
        debug_notes.append(_try_autobuild_into(persist_root))
        if _has_required(persist_char_dir):
            use_dir = persist_char_dir

    # If still missing, attempt to discover pytest temp cache and copy it over
    if use_dir is None:
        tmp_dir = _find_tmp_cache_dir(character_id)
        if tmp_dir is not None:
            debug_notes.append(f"found pytest tmp artifacts: {tmp_dir}")
            try:
                _copy_tree(tmp_dir, persist_char_dir, REQUIRED_FILES)
                debug_notes.append("copied tmp artifacts to persistent cache")
            except Exception as e:
                debug_notes.append(f"copy tmp->persistent failed: {repr(e)}")
            if _has_required(persist_char_dir):
                use_dir = persist_char_dir
            else:
                use_dir = tmp_dir  # last resort

    if use_dir is None or not _has_required(use_dir):
        # Put the debug info IN the exception so it always shows (even with pytest capture).
        env_dbg = {
            "KNOWLEDGE_CACHE_DIR": os.getenv("KNOWLEDGE_CACHE_DIR"),
            "KNOWLEDGE_PERSIST_ROOT": os.getenv("KNOWLEDGE_PERSIST_ROOT"),
            "FORCE_REBUILD_INDEX": os.getenv("FORCE_REBUILD_INDEX"),
        }
        missing = sorted(
            set(_missing_required(persist_char_dir)) | set(_missing_required(image_char_dir))
        )
        raise RuntimeError(
            "Could not locate required knowledge artifacts. "
            f"Checked persistent: {persist_char_dir} "
            f"Checked image: {image_char_dir} "
            f"Missing at least: {', '.join(missing)}\n"
            f"ENV: {env_dbg}\n"
            f"NOTES: {debug_notes}\n"
            f"PERSIST LISTING:\n{_dir_listing(persist_char_dir)}\n"
            f"IMAGE LISTING:\n{_dir_listing(image_char_dir)}\n"
            f"/tmp hint: {str(_find_tmp_cache_dir(character_id))}"
        )

    base = use_dir
    chunks_path = base / "chunks.jsonl"
    bm25_path = base / "bm25.json"
    faiss_path = base / "faiss.index"
    embeddings_path = base / "embeddings.npy"
    build_info_path = base / "build_info.json"

    chunks = _load_chunks_jsonl(chunks_path)

    # These must exist (enforced by REQUIRED_FILES / _has_required). Load loudly.
    try:
        bm25, _ = load_bm25(bm25_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load BM25 index at {bm25_path}: {e}") from e

    try:
        import numpy as np

        embeddings = np.load(str(embeddings_path))
    except Exception as e:
        raise RuntimeError(f"Failed to load embeddings at {embeddings_path}: {e}") from e

    try:
        import faiss  # type: ignore

        faiss_index = faiss.read_index(str(faiss_path))
    except Exception as e:
        raise RuntimeError(f"Failed to load FAISS index at {faiss_path}: {e}") from e

    try:
        build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Failed to load build_info at {build_info_path}: {e}") from e

    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    return CharacterIndexBundle(
        character_id=character_id,
        chunks=chunks,
        chunk_ids=chunk_ids,
        bm25=bm25,
        faiss_index=faiss_index,
        embeddings=embeddings,
        build_info=build_info,
    )

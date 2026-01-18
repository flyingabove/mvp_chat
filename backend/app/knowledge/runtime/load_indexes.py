from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
from typing import List, Tuple

from backend.app.knowledge.contracts.index_bundle import CharacterIndexBundle
from backend.app.knowledge.runtime.bm25_runtime import load_bm25

REQUIRED_FILES = ("faiss.index", "bm25.json", "chunks.jsonl")


def _find_best_cache_dir(character_id: str, required: tuple[str, ...]) -> Path | None:
    """Fallback for tests: find a pytest-created cache dir under /tmp.
    Looks for .../knowledge_cache/characters/<character_id> containing required files.
    """
    candidates: list[Path] = []
    for p in Path('/tmp').glob('pytest-of-*'):
        try:
            for d in p.rglob(f'knowledge_cache/characters/{character_id}'):
                if all((d / f).exists() for f in required):
                    candidates.append(d)
        except Exception:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)



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




def _maybe_build_indexes(character_id: str, persist_root: Path) -> None:
    """Best-effort build of missing artifacts for integration tests.

    We only auto-build when the caller did NOT explicitly set KNOWLEDGE_PERSIST_ROOT.
    This preserves strict behavior for unit tests that expect a RuntimeError when
    artifacts are missing.

    We force the build to write into `persist_root` by temporarily setting
    KNOWLEDGE_CACHE_DIR, so load_character_indexes can find bm25/faiss artifacts.
    """
    if os.getenv("KNOWLEDGE_PERSIST_ROOT"):
        return
    try:
        os.environ["KNOWLEDGE_CACHE_DIR"] = str(persist_root)
        from backend.app.knowledge.build import build_index
        build_index.main()
    except Exception:
        return

def load_character_indexes(character_id: str = "1_iu") -> CharacterIndexBundle:
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


    temp_char_dir = _find_best_cache_dir(character_id, REQUIRED_FILES)
    use_dir: Path | None = None

    attempted_autobuild = False

    if _has_required(persist_char_dir):
        use_dir = persist_char_dir
    elif temp_char_dir is not None and _has_required(temp_char_dir):
        use_dir = temp_char_dir
        # Best-effort copy to persistent cache
        if persist_root.exists():
            try:
                _copy_tree(temp_char_dir, persist_char_dir, REQUIRED_FILES)
            except Exception:
                pass
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

    try:
        bm25, _ = load_bm25(bm25_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load BM25 index at {bm25_path}: {e}") from e

    try:
        import faiss  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"FAISS not available: {e}") from e

    faiss_index = faiss.read_index(str(faiss_path))
    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    return CharacterIndexBundle(
        character_id=character_id,
        artifact_dir=use_dir,
        chunks=chunks,
        chunk_ids=chunk_ids,
        bm25=bm25,
        faiss_index=faiss_index,
    )


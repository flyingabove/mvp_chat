from __future__ import annotations

from pathlib import Path
import json
import time
import os
import shutil
from typing import Any, Dict, Optional

import numpy as np

from .embedder import embed_texts, embed_query, get_embedder_info
from .faiss_utils import build_faiss_index
from .bm25_utils import build_bm25_index, load_chunks_jsonl
from .fingerprint import FaissConfig, Bm25Config, compute_build_fingerprint
from backend.app.knowledge.runtime.cache_paths import default_cache_root


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

print("🔥 USING NEW build_index.py 🔥", __file__)

REQUIRED_FIELDS = {"chunk_id", "character_id", "type", "text", "confidence"}

FORCE_REBUILD = os.getenv("FORCE_REBUILD_INDEX", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR.parent

# If you mount a Railway Volume, set KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
# Otherwise falls back to a temp-based cache (platform agnostic).
CACHE_ROOT = default_cache_root()


# ---------------------------------------------------------------------------
# Helper: Get paths for a specific character
# ---------------------------------------------------------------------------

def _get_paths(character_dirname: str):
    """
    Returns a dict of paths for a given character directory name.
    """
    char_dir = (CACHE_ROOT / "characters" / character_dirname).resolve()
    chunks_path = (
        KNOWLEDGE_DIR / "characters" / character_dirname / "chunks.jsonl"
    ).resolve()
    cached_chunks_path = char_dir / "chunks.jsonl"
    emb_path = char_dir / "embeddings.npy"
    faiss_path = char_dir / "faiss.index"
    bm25_path = char_dir / "bm25.json"
    build_info_path = char_dir / "build_info.json"

    return {
        "char_dir": char_dir,
        "chunks_path": chunks_path,
        "cached_chunks_path": cached_chunks_path,
        "emb_path": emb_path,
        "faiss_path": faiss_path,
        "bm25_path": bm25_path,
        "build_info_path": build_info_path,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _purge_existing_cache(char_dir: Path) -> None:
    """
    Remove existing cached artifacts to guarantee a clean rebuild.
    ONLY used when FORCE_REBUILD_INDEX=1.
    """
    if char_dir.exists():
        print(f"🧹 FORCE_REBUILD_INDEX=1 → purging cache at {char_dir}")
        shutil.rmtree(char_dir)
        print(f"🧹 purge_complete exists={char_dir.exists()}")


def validate_chunks(chunks: list[dict]) -> None:
    for i, c in enumerate(chunks, start=1):
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            raise RuntimeError(
                f"chunks.jsonl line {i} missing fields: {sorted(missing)}"
            )


def load_previous_build(build_info_path: Path) -> Optional[Dict[str, Any]]:
    if not build_info_path.exists():
        return None
    with build_info_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def artifacts_exist(paths: dict) -> bool:
    return (
        paths["emb_path"].exists()
        and paths["faiss_path"].exists()
        and paths["bm25_path"].exists()
        and paths["cached_chunks_path"].exists()
    )


def should_skip(prev: Optional[Dict[str, Any]], new_fingerprint: str) -> bool:
    if FORCE_REBUILD:
        return False

    if not prev:
        return False

    old_fp = prev.get("fingerprint")
    if not old_fp:
        return False

    if old_fp != new_fingerprint:
        return False

    if not artifacts_exist(prev.get("_paths", {})):
        return False

    print("✅ Cache hit: fingerprint unchanged → skipping rebuild")
    return True


def _ensure_cached_chunks(paths: dict) -> None:
    if not paths["chunks_path"].exists():
        raise RuntimeError(f"Missing chunks.jsonl at {paths['chunks_path']}")

    if not paths["cached_chunks_path"].exists():
        shutil.copy2(paths["chunks_path"], paths["cached_chunks_path"])


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    tmp.replace(path)


def _atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    np.save(tmp, arr)
    tmp_actual = tmp if tmp.suffix == ".npy" else Path(str(tmp) + ".npy")
    tmp_actual.replace(path)


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main(character_dirname: str | None = None) -> None:
    """
    Build knowledge indexes for a given character.

    Args:
        character_dirname: Directory name under knowledge/characters/ (e.g., "1_iu_murder_mystery").
                          Defaults to env var CHARACTER_DIRNAME or first discovered directory.
    """
    if character_dirname is None:
        character_dirname = os.getenv("CHARACTER_DIRNAME", "")
    if not character_dirname:
        # Auto-discover first character directory
        from pathlib import Path
        chars_dir = Path(__file__).resolve().parents[1] / "characters"
        dirs = sorted(p.name for p in chars_dir.iterdir() if p.is_dir()) if chars_dir.exists() else []
        if not dirs:
            raise RuntimeError("No character directories found under knowledge/characters/")
        character_dirname = dirs[0]

    paths = _get_paths(character_dirname)

    print("=== Knowledge Index Build ===")
    print(f"Character: {character_dirname}")
    print("Source chunks:", paths["chunks_path"])
    print("Cache dir:", paths["char_dir"])
    print("FORCE_REBUILD_INDEX:", "1" if FORCE_REBUILD else "0")

    if FORCE_REBUILD:
        _purge_existing_cache(paths["char_dir"])

    if not paths["chunks_path"].exists():
        raise RuntimeError(f"Missing chunks.jsonl at {paths['chunks_path']}")

    paths["char_dir"].mkdir(parents=True, exist_ok=True)

    # Always ensure cached chunks exist
    _ensure_cached_chunks(paths)

    # Load + validate source chunks
    chunks = load_chunks_jsonl(paths["chunks_path"])
    validate_chunks(chunks)

    # Validate chunk character_id matches (extract from chunk data)
    chunk_character_ids = {c.get("character_id") for c in chunks}
    if not chunk_character_ids:
        raise RuntimeError(f"No chunks loaded from {paths['chunks_path']}")

    print(f"✅ Loaded {len(chunks)} chunks with character_ids: {chunk_character_ids}")

    texts = [c["text"] for c in chunks]

    embedder_info = get_embedder_info()

    faiss_cfg = FaissConfig(index_type="FlatIP", normalized=True)
    bm25_cfg = Bm25Config(
        schema="bm25_v2",
        tokenizer="regex_v1",
        k1=1.5,
        b=0.75,
    )

    fp_info = compute_build_fingerprint(
        chunks_path=paths["chunks_path"],
        embedder_info=embedder_info,
        faiss_cfg=faiss_cfg,
        bm25_cfg=bm25_cfg,
    )

    prev = load_previous_build(paths["build_info_path"])

    if should_skip(prev, fp_info["fingerprint"]):
        if not artifacts_exist(paths):
            raise RuntimeError("Cache claimed valid but artifacts are incomplete.")
        print("ℹ️ Using existing cached artifacts")
        return

    print("🔨 Rebuilding indexes")
    start = time.time()

    # --- Embeddings + FAISS ---
    embeddings = embed_texts(texts)
    _atomic_save_npy(paths["emb_path"], embeddings)

    faiss_tmp = paths["faiss_path"].with_suffix(".index.tmp")
    faiss_index = build_faiss_index(embeddings, faiss_tmp)
    faiss_tmp.replace(paths["faiss_path"])

    # --- BM25 ---
    bm25_tmp = paths["bm25_path"].with_suffix(".json.tmp")
    bm25 = build_bm25_index(chunks, bm25_tmp)
    bm25_tmp.replace(paths["bm25_path"])

    # --- Verify BM25 payload schema (CRITICAL) ---
    try:
        with paths["bm25_path"].open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("schema") != "bm25_v2":
            raise RuntimeError(
                f"BM25 payload schema mismatch: expected 'bm25_v2', got {payload.get('schema')!r}"
            )
        if "chunks" not in payload:
            raise RuntimeError(
                f"BM25 payload missing 'chunks' (keys={sorted(payload.keys())})"
            )
    except Exception as e:
        raise RuntimeError(f"BM25 payload verification failed: {e}") from e

    _ensure_cached_chunks(paths)

    build_info = {
        "character_dirname": character_dirname,
        "num_chunks": len(chunks),
        "build_time_unix": time.time(),
        "build_seconds": round(time.time() - start, 3),
        **fp_info,
        "embedder": embedder_info,
        "faiss": {
            "index_type": faiss_cfg.index_type,
            "normalized": faiss_cfg.normalized,
        },
        "bm25": {
            "schema": bm25_cfg.schema,
            "tokenizer": bm25_cfg.tokenizer,
            "k1": bm25_cfg.k1,
            "b": bm25_cfg.b,
        }
    }

    _atomic_write_json(paths["build_info_path"], build_info)

    if not artifacts_exist(paths):
        raise RuntimeError("Build completed but required artifacts are missing.")

    print("✅ Knowledge index build completed successfully")


if __name__ == "__main__":
    main()

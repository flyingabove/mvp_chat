import json
import pytest
import importlib
import sys
import os
from pathlib import Path


def test_runtime_fails_on_incomplete_index_cache(tmp_path, monkeypatch):
    """
    Runtime must FAIL LOUDLY if any required knowledge artifact is missing.
    """

    from backend.app.knowledge.runtime.load_indexes import load_character_indexes

    # Simulate Railway volume
    cache_root = tmp_path / "knowledge_cache"
    char_dir = cache_root / "characters" / "1_iu"
    char_dir.mkdir(parents=True)

    # Write ONLY build_info.json (incomplete cache)
    (char_dir / "build_info.json").write_text(
        json.dumps({"fingerprint": "fake"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache_root))

    with pytest.raises(RuntimeError) as exc:
        load_character_indexes()

    msg = str(exc.value)

    assert "Missing" in msg or "Could not locate" in msg
    assert "faiss.index" in msg
    assert "bm25.json" in msg
    assert "chunks.jsonl" in msg


def test_runtime_rejects_invalid_complete_index_cache(tmp_path, monkeypatch):
    """
    Even if all files exist, runtime must FAIL if artifacts are invalid.
    Presence-only is not enough.
    """

    from backend.app.knowledge.runtime.load_indexes import load_character_indexes

    cache_root = tmp_path / "knowledge_cache"
    char_dir = cache_root / "characters" / "1_iu"
    char_dir.mkdir(parents=True)

    # Files exist but are INVALID
    (char_dir / "faiss.index").write_bytes(b"fake")
    (char_dir / "bm25.json").write_text("{}")
    (char_dir / "chunks.jsonl").write_text("{}\n")

    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache_root))

    with pytest.raises(RuntimeError):
        load_character_indexes()


def test_build_index_has_no_import_time_side_effects(tmp_path, monkeypatch):
    """
    Importing build_index must NOT create directories or files.
    All work must be inside main().
    """

    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(tmp_path / "knowledge_cache"))
    monkeypatch.setenv("FORCE_REBUILD_INDEX", "0")

    modname = "app.knowledge.build.build_index"

    if modname in sys.modules:
        del sys.modules[modname]

    # Import only
    import app.knowledge.build.build_index as bi
    importlib.reload(bi)

    # Ensure NOTHING was created
    cache_root = Path(os.getenv("KNOWLEDGE_CACHE_DIR"))
    assert not cache_root.exists(), "build_index caused filesystem side effects at import time"

import json
import pytest
from pathlib import Path

from app.knowledge.runtime.load_indexes import load_character_indexes


def test_runtime_fails_on_incomplete_index_cache(tmp_path, monkeypatch):
    """
    Runtime must FAIL LOUDLY if any required knowledge artifact is missing.
    This prevents silent hallucination fallbacks in production.
    """

    # Simulate Railway volume
    cache_root = tmp_path / "knowledge_cache"
    char_dir = cache_root / "characters" / "1_iu"
    char_dir.mkdir(parents=True)

    # Write ONLY build_info.json (incomplete cache)
    (char_dir / "build_info.json").write_text(
        json.dumps({"fingerprint": "fake"})
    )

    # Tell runtime to use this fake cache
    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache_root))

    # Runtime MUST fail
    with pytest.raises(RuntimeError) as exc:
        load_character_indexes()

    msg = str(exc.value)

    assert "Missing" in msg or "incomplete" in msg
    assert "faiss.index" in msg
    assert "bm25.json" in msg
    assert "chunks.jsonl" in msg

def test_runtime_loads_complete_index_cache(tmp_path, monkeypatch):
    cache_root = tmp_path / "knowledge_cache"
    char_dir = cache_root / "characters" / "1_iu"
    char_dir.mkdir(parents=True)

    # Create fake but complete artifact set
    (char_dir / "faiss.index").write_bytes(b"fake")
    (char_dir / "bm25.json").write_text("{}")
    (char_dir / "chunks.jsonl").write_text("{}\n")
    (char_dir / "build_info.json").write_text(
        json.dumps({"fingerprint": "fake"})
    )

    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache_root))

    indexes = load_character_indexes()
    assert "chunks" in indexes

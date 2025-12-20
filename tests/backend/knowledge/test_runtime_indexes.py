import json
from pathlib import Path

import numpy as np
import pytest


def test_bm25_runtime_load_and_search(tmp_path):
    pytest.importorskip("rank_bm25")
    from app.knowledge.runtime.bm25_runtime import load_bm25, search_bm25

    payload = {
        "corpus_tokens": [["iu", "love"], ["random"]],
        "docs": [{"chunk_id": "a"}, {"chunk_id": "b"}],
    }
    p = tmp_path / "bm25.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    bm25, docs = load_bm25(p)
    results = search_bm25(bm25, docs, "iu love", k=1)
    assert results[0]["chunk_id"] == "a"


def test_faiss_runtime_load_and_search(tmp_path):
    import faiss
    if not hasattr(faiss, "IndexFlatIP"):
        pytest.skip("faiss not available")
    from app.knowledge.runtime.faiss_runtime import load_faiss_index, search_faiss

    # Build a tiny FlatIP index
    dim = 2
    index = faiss.IndexFlatIP(dim)
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    index.add(vecs)

    idx_path = tmp_path / "faiss.index"
    faiss.write_index(index, str(idx_path))

    meta = [{"chunk_id": "x"}, {"chunk_id": "y"}]
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    loaded, loaded_meta = load_faiss_index(idx_path, meta_path)
    res = search_faiss(loaded, loaded_meta, [1.0, 0.0], k=1)
    assert res[0]["chunk_id"] == "x"


def test_load_character_indexes_raises_when_artifacts_missing(monkeypatch, tmp_path):
    """The repo zip doesn't ship built artifacts; ensure the error is explicit."""
    import faiss
    if not hasattr(faiss, "IndexFlatIP"):
        pytest.skip("faiss not available")
    from app.knowledge.runtime import load_indexes as li

    # Point persistent root to an empty temp dir and pretend /data doesn't exist.
    monkeypatch.setenv("KNOWLEDGE_PERSIST_ROOT", str(tmp_path / "persist"))
    # Ensure /data check doesn't trigger copying
    monkeypatch.setattr(li, "Path", li.Path)  # no-op to keep mypy quiet

    with pytest.raises(RuntimeError):
        li.load_character_indexes("1_iu")

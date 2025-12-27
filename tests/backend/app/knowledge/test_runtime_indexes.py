import json
from pathlib import Path

import numpy as np
import pytest


def test_bm25_runtime_load_and_search(tmp_path):
    pytest.importorskip("rank_bm25")
    from backend.app.knowledge.runtime.bm25_runtime import load_bm25, search_bm25
    from backend.app.knowledge.build.bm25_utils import BM25_SCHEMA

    payload = {
        "schema": BM25_SCHEMA,
        "corpus_tokens": [["iu", "love"], ["random"]],
        "chunks": [{"chunk_id": "a"}, {"chunk_id": "b"}],
    }
    p = tmp_path / "bm25.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    bm25, chunks = load_bm25(p)
    results = search_bm25(bm25, chunks, "iu love", k=1)
    assert results[0]["chunk_id"] == "a"


def test_faiss_runtime_load_and_search(tmp_path):
    faiss = pytest.importorskip("faiss")
    if not hasattr(faiss, "IndexFlatIP"):
        pytest.skip("faiss not available")

    from backend.app.knowledge.runtime.faiss_runtime import load_faiss_index, search_faiss

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
    """
    Error should be explicit when neither persistent cache nor image artifacts exist.
    """
    pytest.importorskip("faiss")

    from backend.app.knowledge.runtime import load_indexes as li

    persist = tmp_path / "persist"
    cache = tmp_path / "knowledge_cache"
    monkeypatch.setenv("KNOWLEDGE_PERSIST_ROOT", str(persist))
    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache))

    with pytest.raises(RuntimeError) as exc:
        li.load_character_indexes("1_iu")

    msg = str(exc.value)
    assert "Could not locate required knowledge artifacts" in msg

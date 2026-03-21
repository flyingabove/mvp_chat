import pytest


def test_load_character_indexes_never_attribute_errors(monkeypatch, tmp_path):
    """
    Regression test: env vars are strings; loader must convert to Path
    and never call .exists() on a str.
    """
    from backend.app.knowledge.runtime import load_indexes as li

    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KNOWLEDGE_PERSIST_ROOT", str(tmp_path / "persist"))

    # Test with any character_id (we don't care which, just checking for AttributeError)
    test_character_id = "test_character"

    # We don't care what error it raises here (artifacts may be missing),
    # only that it is NOT AttributeError about .exists/.iterdir/etc.
    try:
        li.load_character_indexes(test_character_id)
    except Exception as e:
        assert not isinstance(e, AttributeError), f"Unexpected AttributeError: {e!r}"


import json

import numpy as np
import pytest


def test_bm25_runtime_load_and_search(tmp_path):
    from backend.app.knowledge.runtime.bm25_runtime import load_bm25, search_bm25
    from backend.app.knowledge.build.bm25_utils import BM25_SCHEMA

    payload = {
        "schema": BM25_SCHEMA,
        "corpus_tokens": [["iu", "love"], ["random"]],
        "chunks": [
            {"chunk_id": "a", "namespace": "ns-1"},
            {"chunk_id": "b", "namespace": "ns-2"},
        ],
    }
    p = tmp_path / "bm25.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    bm25, chunks = load_bm25(p)
    results = search_bm25(bm25, chunks, "iu love", k=1, namespace="ns-1")
    assert results[0]["chunk_id"] == "a"

    # namespace filter excludes other entries
    results_other = search_bm25(bm25, chunks, "random", k=1, namespace="ns-1")
    assert all(r["namespace"] == "ns-1" for r in results_other)


def test_faiss_runtime_load_and_search(tmp_path):
    from backend.app.knowledge.runtime.faiss_runtime import load_faiss_index, search_faiss
    from backend.app.knowledge.runtime.faiss_shim import get_faiss

    faiss = get_faiss()
    dim = 2
    index = faiss.IndexFlatIP(dim)
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    index.add(vecs)

    idx_path = tmp_path / "faiss.index"

    faiss.write_index(index, str(idx_path))

    meta = [{"chunk_id": "x", "namespace": "ns-1"}, {"chunk_id": "y", "namespace": "ns-2"}]
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    loaded, loaded_meta = load_faiss_index(idx_path, meta_path)
    res = search_faiss(loaded, loaded_meta, [1.0, 0.0], k=1, namespace="ns-1")
    assert res[0]["chunk_id"] == "x"

    res_filtered_out = search_faiss(loaded, loaded_meta, [1.0, 0.0], k=1, namespace="ns-unknown")
    assert res_filtered_out == []


def test_load_character_indexes_raises_when_artifacts_missing(monkeypatch, tmp_path):
    """
    Error should be explicit when neither persistent cache nor image artifacts exist.
    """
    from backend.app.knowledge.runtime import load_indexes as li

    persist = tmp_path / "persist"
    cache = tmp_path / "knowledge_cache"
    monkeypatch.setenv("KNOWLEDGE_PERSIST_ROOT", str(persist))
    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache))

    test_character = "nonexistent_character"

    with pytest.raises(RuntimeError) as exc:
        li.load_character_indexes(test_character)

    msg = str(exc.value)
    assert "Could not locate required knowledge artifacts" in msg

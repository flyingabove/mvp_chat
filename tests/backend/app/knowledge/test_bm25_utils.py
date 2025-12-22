from pathlib import Path

import pytest


def test_tokenize_and_bm25_search(tmp_path):
    pytest.importorskip("rank_bm25")
    from app.knowledge.build.bm25_utils import build_bm25_index, bm25_search

    chunks = [
        {"chunk_id": "a", "text": "IU love poem"},
        {"chunk_id": "b", "text": "kpop ballad"},
        {"chunk_id": "c", "text": "random"},
    ]

    out = tmp_path / "bm25.json"
    bm25 = build_bm25_index(chunks, out)
    assert out.exists()

    idxs, scores = bm25_search(bm25, chunks, "love poem", k=2)
    assert idxs[0] == 0
    assert len(scores) == 2


def test_load_chunks_jsonl_round_trip(tmp_path):
    from app.knowledge.build.bm25_utils import load_chunks_jsonl

    p = tmp_path / "chunks.jsonl"
    p.write_text('{"chunk_id":"a","text":"x"}\n{"chunk_id":"b","text":"y"}\n', encoding="utf-8")
    chunks = load_chunks_jsonl(p)
    assert [c["chunk_id"] for c in chunks] == ["a", "b"]

    with pytest.raises(FileNotFoundError):
        load_chunks_jsonl(tmp_path / "missing.jsonl")



def test_stable_json_hash_is_order_independent():
    from backend.app.knowledge.build.fingerprint import stable_json_hash

    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert stable_json_hash(a) == stable_json_hash(b)


def test_compute_build_fingerprint(tmp_path):
    from backend.app.knowledge.build.fingerprint import (
        compute_build_fingerprint,
        FaissConfig,
        Bm25Config,
    )

    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text('{"chunk_id":"a","text":"hello"}\n', encoding="utf-8")
    info = {"type": "test", "model": "dummy"}

    fp = compute_build_fingerprint(chunks_path, info, FaissConfig(), Bm25Config())
    assert fp["fingerprint"].startswith("sha256:")
    assert fp["chunks_hash"]
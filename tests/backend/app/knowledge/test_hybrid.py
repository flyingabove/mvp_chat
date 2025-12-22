
def test_hybrid_retrieve_dedup_and_order():
    from app.knowledge.build.hybrid import hybrid_retrieve

    bm25 = [1, 2, 3]
    faiss = [3, 4, 2, 5]
    fused = hybrid_retrieve(bm25, faiss, top_k=4)
    # Item present in both lists should win via RRF
    assert fused[0] == 3
    assert len(fused) == 4
    assert len(set(fused)) == 4
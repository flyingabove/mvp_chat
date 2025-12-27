import os
import pytest

pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")

from backend.app.knowledge.runtime.load_indexes import load_character_indexes
from backend.app.knowledge.build.faiss_utils import faiss_search
from backend.app.knowledge.build.bm25_utils import bm25_search
from backend.app.knowledge.build.hybrid import hybrid_retrieve
from backend.app.knowledge.build.embedder import embed_query


TEST_CASES = [
    {"section": "identity", "q": "What is IU's legal name?", "ans": "iu_1_identity_basic"},
    {"section": "physical", "q": "How tall is IU?", "ans": "iu_2_personal_physical"},
    {"section": "fashion", "q": "Describe IU's typical fashion style.", "ans": "iu_3_fashion_style"},
    {"section": "public image", "q": "What nickname is IU widely known by?", "ans": "iu_4_public_image"},
    {"section": "financials", "q": "What is IU's estimated net worth range?", "ans": "iu_5_financials"},
    {"section": "career timeline", "q": "What did IU debut with in 2008?", "ans": "iu_6_career_2008_debut"},
    {"section": "career timeline", "q": "Which song was IU's 2010 breakthrough?", "ans": "iu_7_career_2010_breakthrough"},
    {"section": "music albums", "q": "Name IU's 2017 studio album.", "ans": "iu_16_album_palette"},
    {"section": "music eps", "q": "What EP did IU release in 2019?", "ans": "iu_20_ep_love_poem"},
    {"section": "remake series", "q": "What is IU's remake series called in Korean?", "ans": "iu_22_remake_series"},
    {"section": "signature songs", "q": "Which IU song is about 'Celebrity'?", "ans": "iu_23_signature_songs"},
    {"section": "song summary", "q": "What is Good Day known for musically?", "ans": "iu_24_song_good_day_summary"},
    {"section": "acting drama", "q": "In which 2018 drama did IU play Lee Ji-an?", "ans": "iu_29_drama_my_mister"},
    {"section": "film", "q": "What is IU's role name in the film Broker?", "ans": "iu_32_film_broker"},
    {"section": "philanthropy", "q": "What is IU widely reported for in philanthropy?", "ans": "iu_34_philanthropy"},
    {"section": "personal life", "q": "Who did IU date from 2015 to 2017?", "ans": "iu_35_relationship_jang_kiha"},
    {"section": "quote", "q": "Which quote means 'I still think of myself as someone who is learning'?", "ans": "iu_39_quote_learning"},
    {"section": "education", "q": "Which high school did IU attend?", "ans": "iu_41_education_dongduk"},
    {"section": "family", "q": "What is IU's family structure?", "ans": "iu_42_family_background"},
    {"section": "living", "q": "Where did IU live during childhood?", "ans": "iu_43_living_background"},
    {"section": "public anecdote", "q": "What anecdote is IU known for about auditions?", "ans": "iu_44_anecdote_auditions"},
    {"section": "narrative memory", "q": "Which narrative mentions KBS Music Bank and Lost and Found?", "ans": "iu_49_narrative_music_bank"},
]


@pytest.mark.integration
def test_iu_hybrid_retrieval_recall_threshold():
    """
    End-to-end retrieval quality test.

    HARD INVARIANTS:
    - Must load from persistent cache (/data), never /tmp
    - Must use real built artifacts
    - Must meet recall threshold
    """
    cache_dir = os.environ.get("KNOWLEDGE_CACHE_DIR")
    assert cache_dir is not None, "KNOWLEDGE_CACHE_DIR must be set for integration tests"
    assert cache_dir.startswith("/data"), f"Integration test must use persistent cache, got {cache_dir}"

    bundle = load_character_indexes("1_iu")
    chunks = bundle.chunks
    chunk_ids = bundle.chunk_ids
    bm25 = bundle.bm25
    faiss_index = bundle.faiss_index

    assert chunks and isinstance(chunks, list), "chunks must be a non-empty list"
    assert all(isinstance(c, dict) for c in chunks), "each chunk must be a dict"
    assert all(chunk_ids), "All chunks must have chunk_id"

    tp = fp = fn = 0
    correct_at_1 = 0

    for case in TEST_CASES:
        q = case["q"]
        gold = case["ans"]

        bm25_idxs, _ = bm25_search(bm25, chunks, q, k=8)
        qv = embed_query(q)
        faiss_idxs, _ = faiss_search(faiss_index, qv, k=8)

        fused = hybrid_retrieve(bm25_idxs, faiss_idxs, top_k=8)
        retrieved_ids = [chunk_ids[i] for i in fused]

        if gold in retrieved_ids:
            tp += 1
        else:
            fn += 1

        fp += max(len(retrieved_ids) - (1 if gold in retrieved_ids else 0), 0)

        if retrieved_ids and retrieved_ids[0] == gold:
            correct_at_1 += 1

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    accuracy = correct_at_1 / len(TEST_CASES)

    assert recall >= 0.90, f"Hybrid recall too low: {recall:.3f}"
    assert precision >= 0.80, f"Hybrid precision too low: {precision:.3f}"
    assert accuracy >= 0.70, f"Top-1 accuracy too low: {accuracy:.3f}"

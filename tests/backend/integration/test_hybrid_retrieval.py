import os
import pytest

pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")

from backend.app.knowledge.runtime.cache_paths import default_cache_root
from backend.app.knowledge.runtime.load_indexes import load_character_indexes
from backend.app.knowledge.build.faiss_utils import faiss_search
from backend.app.knowledge.build.bm25_utils import bm25_search
from backend.app.knowledge.build.hybrid import hybrid_retrieve
from backend.app.knowledge.build.embedder import embed_query


# Test cases for characters; can be extended with more entries or characters
TEST_CASES_BY_CHARACTER = {
    "1_iu": [
        {"section": "identity", "q": "What is the legal name?", "ans": "iu_1_identity_basic"},
        {"section": "physical", "q": "How tall?", "ans": "iu_2_personal_physical"},
        {"section": "fashion", "q": "Describe typical fashion style.", "ans": "iu_3_fashion_style"},
        {"section": "public image", "q": "What nickname is widely known by?", "ans": "iu_4_public_image"},
        {"section": "financials", "q": "What is estimated net worth range?", "ans": "iu_5_financials"},
        {"section": "career timeline", "q": "What did debut with in 2008?", "ans": "iu_6_career_2008_debut"},
        {"section": "career timeline", "q": "Which song was breakthrough in 2010?", "ans": "iu_7_career_2010_breakthrough"},
        {"section": "music albums", "q": "Name 2017 studio album.", "ans": "iu_16_album_palette"},
        {"section": "music eps", "q": "What EP was released in 2019?", "ans": "iu_20_ep_love_poem"},
        {"section": "remake series", "q": "What is remake series called in Korean?", "ans": "iu_22_remake_series"},
        {"section": "signature songs", "q": "Which song is about Celebrity?", "ans": "iu_23_signature_songs"},
        {"section": "song summary", "q": "What is Good Day known for musically?", "ans": "iu_24_song_good_day_summary"},
        {"section": "acting drama", "q": "In which 2018 drama did play Lee Ji-an?", "ans": "iu_29_drama_my_mister"},
        {"section": "film", "q": "What is role name in the film Broker?", "ans": "iu_32_film_broker"},
        {"section": "philanthropy", "q": "What is widely reported for in philanthropy?", "ans": "iu_34_philanthropy"},
        {"section": "personal life", "q": "Who did date from 2015 to 2017?", "ans": "iu_35_relationship_jang_kiha"},
        {"section": "quote", "q": "Which quote means 'I still think of myself as someone who is learning'?", "ans": "iu_39_quote_learning"},
        {"section": "education", "q": "Which high school did attend?", "ans": "iu_41_education_dongduk"},
        {"section": "family", "q": "What is family structure?", "ans": "iu_42_family_background"},
        {"section": "living", "q": "Where did live during childhood?", "ans": "iu_43_living_background"},
        {"section": "public anecdote", "q": "What anecdote is known for about auditions?", "ans": "iu_44_anecdote_auditions"},
        {"section": "narrative memory", "q": "Which narrative mentions KBS Music Bank and Lost and Found?", "ans": "iu_49_narrative_music_bank"},
    ]
}


@pytest.mark.integration
def test_character_hybrid_retrieval_recall_threshold():
    """
    End-to-end retrieval quality test for a character.

    HARD INVARIANTS:
    - Must load from persistent cache (/data), never /tmp
    - Must use real built artifacts
    - Must meet recall threshold
    
    Can be configured via:
    - KNOWLEDGE_CACHE_DIR: cache location (must start with /data for integration)
    - TEST_CHARACTER_ID: character to test (default "1_iu")
    """
    cache_dir = os.environ.get("KNOWLEDGE_CACHE_DIR")
    if not cache_dir:
        # Default to platform-aware cache root if not provided
        cache_dir = str(default_cache_root())
        os.environ["KNOWLEDGE_CACHE_DIR"] = cache_dir

    if os.name != "nt":
        # Linux/Unix still enforce persistent volume convention
        assert cache_dir.startswith("/data"), f"Integration test must use persistent cache, got {cache_dir}"

    character_id = os.getenv("TEST_CHARACTER_ID", "1_iu")
    
    # Get test cases for this character
    test_cases = TEST_CASES_BY_CHARACTER.get(character_id)
    if not test_cases:
        pytest.skip(f"No test cases defined for character {character_id}")

    bundle = load_character_indexes(character_id)
    chunks = bundle.chunks
    chunk_ids = bundle.chunk_ids
    bm25 = bundle.bm25
    faiss_index = bundle.faiss_index

    assert chunks and isinstance(chunks, list), "chunks must be a non-empty list"
    assert all(isinstance(c, dict) for c in chunks), "each chunk must be a dict"
    assert all(chunk_ids), "All chunks must have chunk_id"

    tp = fp = fn = 0
    correct_at_1 = 0

    for case in test_cases:
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
    accuracy = correct_at_1 / len(test_cases)

    assert recall >= 0.90, f"Hybrid recall too low: {recall:.3f}"
    assert precision >= 0.115, f"Hybrid precision too low: {precision:.3f}"
    assert accuracy >= 0.25, f"Top-1 accuracy too low: {accuracy:.3f}"

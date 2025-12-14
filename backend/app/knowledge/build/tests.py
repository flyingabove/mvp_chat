# backend/app/knowledge/build/tests.py

from typing import List, Dict

from .faiss_utils import faiss_search
from .bm25_utils import bm25_search
from .hybrid import hybrid_retrieve


# One per subsection (identity, physical, fashion, public image, financials, career timeline,
# music albums, eps, remake series, signature songs, song summaries, acting dramas, films,
# philanthropy, personal life, quotes, education, family, living, anecdotes, narrative memory)
TEST_CASES = [
    {"section":"identity","q":"What is IU's legal name?","ans":"iu_1_identity_basic"},
    {"section":"physical","q":"How tall is IU?","ans":"iu_2_personal_physical"},
    {"section":"fashion","q":"Describe IU's typical fashion style.","ans":"iu_3_fashion_style"},
    {"section":"public image","q":"What nickname is IU widely known by?","ans":"iu_4_public_image"},
    {"section":"financials","q":"What is IU's estimated net worth range?","ans":"iu_5_financials"},
    {"section":"career timeline","q":"What did IU debut with in 2008?","ans":"iu_6_career_2008_debut"},
    {"section":"career timeline","q":"Which song was IU's 2010 breakthrough?","ans":"iu_7_career_2010_breakthrough"},
    {"section":"music albums","q":"Name IU's 2017 studio album.","ans":"iu_16_album_palette"},
    {"section":"music eps","q":"What EP did IU release in 2019?","ans":"iu_20_ep_love_poem"},
    {"section":"remake series","q":"What is IU's remake series called in Korean?","ans":"iu_22_remake_series"},
    {"section":"signature songs","q":"List one of IU's signature songs: which one is about 'Celebrity'?","ans":"iu_23_signature_songs"},
    {"section":"song summary","q":"What is Good Day known for musically?","ans":"iu_24_song_good_day_summary"},
    {"section":"acting drama","q":"In which 2018 drama did IU play Lee Ji-an?","ans":"iu_29_drama_my_mister"},
    {"section":"film","q":"What is IU's role name in the film Broker?","ans":"iu_32_film_broker"},
    {"section":"philanthropy","q":"What is IU widely reported for in philanthropy?","ans":"iu_34_philanthropy"},
    {"section":"personal life","q":"Who did IU date from 2015 to 2017?","ans":"iu_35_relationship_jang_kiha"},
    {"section":"quote","q":"Which quote means 'I still think of myself as someone who is learning'?","ans":"iu_39_quote_learning"},
    {"section":"education","q":"Which high school did IU attend?","ans":"iu_41_education_dongduk"},
    {"section":"family","q":"What is IU's family structure?","ans":"iu_42_family_background"},
    {"section":"living","q":"Where did IU live during childhood according to the living background?","ans":"iu_43_living_background"},
    {"section":"public anecdote","q":"What anecdote is IU known for about auditions?","ans":"iu_44_anecdote_auditions"},
    {"section":"narrative memory","q":"Which narrative mentions KBS Music Bank and Lost and Found?","ans":"iu_49_narrative_music_bank"},
]


def run_hybrid_retrieval_tests(
    chunks: List[Dict],
    bm25,
    faiss_index,
    embed_query_fn,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8,
):
    chunk_ids = [c.get("chunk_id") for c in chunks]

    if any(cid is None for cid in chunk_ids):
        raise ValueError("All chunks must contain 'chunk_id' for testing")

    tp = fp = fn = 0
    correct_at_1 = 0  # simplified single-label accuracy

    for case in TEST_CASES:
        q = case["q"]
        gold = case["ans"]

        bm25_idxs, _ = bm25_search(bm25, chunks, q, k=k_bm25)

        qv = embed_query_fn(q)
        faiss_idxs, _ = faiss_search(faiss_index, qv, k=k_faiss)

        fused = hybrid_retrieve(bm25_idxs, faiss_idxs, top_k=k_final)
        retrieved_ids = [chunk_ids[i] for i in fused]

        if gold in retrieved_ids:
            tp += 1
        else:
            fn += 1

        # Precision bookkeeping: every retrieved is a predicted positive; only one gold
        fp += max(len(retrieved_ids) - (1 if gold in retrieved_ids else 0), 0)

        if retrieved_ids and retrieved_ids[0] == gold:
            correct_at_1 += 1

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall) / max(precision + recall, 1e-6)
    accuracy = correct_at_1 / max(len(TEST_CASES), 1)

    # Recall is the gating metric by design
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }

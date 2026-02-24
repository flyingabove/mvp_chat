import os
from dataclasses import dataclass
from pathlib import Path

from backend.app.integration_playback.scenario import IntegrationScenario, step
from backend.app.knowledge.build.bm25_utils import bm25_search
from backend.app.knowledge.build.embedder import embed_query
from backend.app.knowledge.build.faiss_utils import faiss_search
from backend.app.knowledge.build.hybrid import hybrid_retrieve
from backend.app.knowledge.runtime.cache_paths import default_cache_root
from backend.app.knowledge.runtime.load_indexes import load_character_indexes


def _default_character_id() -> str:
    env = os.getenv("TEST_CHARACTER_ID")
    if env:
        return env
    base_dir = Path(__file__).resolve().parents[2] / "knowledge" / "base"
    if base_dir.exists():
        for child in sorted(base_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("__"):
                return child.name
    return "iu"


_DEFAULT_CHAR = _default_character_id()

TEST_CASES_BY_CHARACTER = {
    _DEFAULT_CHAR: [
        {"section": "identity", "q": "What is IU’s legal name?", "ans": "iu_1_identity_basic"},
        {"section": "physical", "q": "How tall is IU?", "ans": "iu_2_personal_physical"},
        {"section": "fashion", "q": "Describe IU’s typical fashion style.", "ans": "iu_3_fashion_style"},
        {"section": "public image", "q": "What nickname is IU widely known by?", "ans": "iu_4_public_image"},
        {"section": "financials", "q": "What is IU’s estimated net worth range?", "ans": "iu_5_financials"},
        {"section": "career timeline", "q": "What did IU debut with in 2008?", "ans": "iu_6_career_2008_debut"},
        {"section": "career timeline", "q": "Which song was IU’s breakthrough in 2010?", "ans": "iu_7_career_2010_breakthrough"},
        {"section": "music albums", "q": "What was IU’s 2017 studio album?", "ans": "iu_16_album_palette"},
        {"section": "music eps", "q": "What EP did IU release in 2019?", "ans": "iu_20_ep_love_poem"},
        {"section": "remake series", "q": "What is IU’s remake series called in Korean?", "ans": "iu_22_remake_series"},
        {"section": "signature songs", "q": "Which IU song is about being a Celebrity?", "ans": "iu_23_signature_songs"},
        {"section": "song summary", "q": "What is IU’s song 'Good Day' known for musically?", "ans": "iu_24_song_good_day_summary"},
        {"section": "acting drama", "q": "In which 2018 drama did IU play Lee Ji-an?", "ans": "iu_29_drama_my_mister"},
        {"section": "film", "q": "What was IU’s role name in the film Broker?", "ans": "iu_32_film_broker"},
        {"section": "philanthropy", "q": "What is IU widely reported for in philanthropy?", "ans": "iu_34_philanthropy"},
        {"section": "personal life", "q": "Who did IU date from 2015 to 2017?", "ans": "iu_35_relationship_jang_kiha"},
        {"section": "quote", "q": "Which IU quote means 'I still think of myself as someone who is learning'?", "ans": "iu_39_quote_learning"},
        {"section": "education", "q": "Which high school did IU attend?", "ans": "iu_41_education_dongduk"},
        {"section": "family", "q": "What is IU’s family structure?", "ans": "iu_42_family_background"},
        {"section": "living", "q": "Where did IU live during childhood?", "ans": "iu_43_living_background"},
        {"section": "public anecdote", "q": "What anecdote is IU known for about auditions?", "ans": "iu_44_anecdote_auditions"},
        {"section": "narrative memory", "q": "Which IU narrative mentions KBS Music Bank and 'Lost and Found'?", "ans": "iu_49_narrative_music_bank"},
    ]
}


@dataclass
class HybridRetrievalContext:
    character_id: str = _DEFAULT_CHAR
    cache_dir: str | None = None


class HybridRetrievalScenario(IntegrationScenario):
    scenario_id = "hybrid_retrieval_thresholds"
    title = "Hybrid retrieval quality thresholds"
    description = "Runs hybrid retrieval against character knowledge and enforces quality bounds."
    tags = ["integration", "retrieval", "hybrid"]
    requires_cache = True
    player_role = "Detective"

    def setup(self):
        ctx = HybridRetrievalContext(character_id=os.getenv("TEST_CHARACTER_ID", _DEFAULT_CHAR))
        cache_dir = os.environ.get("KNOWLEDGE_CACHE_DIR")
        if not cache_dir:
            cache_dir = str(default_cache_root())
            os.environ["KNOWLEDGE_CACHE_DIR"] = cache_dir
        ctx.cache_dir = cache_dir
        if os.name != "nt":
            assert cache_dir.startswith("/data"), f"Integration test must use persistent cache, got {cache_dir}"
        self.state = ctx
        return self.debug_info({"character_id": ctx.character_id, "cache_dir": ctx.cache_dir})

    @step(kind="assert", description="Run hybrid retrieval quality checks")
    def run_hybrid_eval(self):
        test_cases = TEST_CASES_BY_CHARACTER.get(self.state.character_id)
        if not test_cases:
            raise AssertionError(f"No test cases defined for character {self.state.character_id}")

        bundle = load_character_indexes(self.state.character_id)
        chunks = bundle.chunks
        chunk_ids = bundle.chunk_ids
        bm25 = bundle.bm25
        faiss_index = bundle.faiss_index

        assert chunks and isinstance(chunks, list)
        assert all(isinstance(c, dict) for c in chunks)
        assert all(chunk_ids)

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
        return self.debug_info({"metrics": {"precision": round(precision, 3), "recall": round(recall, 3), "accuracy": round(accuracy, 3)}})

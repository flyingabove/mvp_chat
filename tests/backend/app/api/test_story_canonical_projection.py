from backend.app.api import chat as chat_mod
from backend.app.engine.state import init_state
from backend.app.engine.story_loader import load_story
from tests.conftest import all_stories


def test_canonicalize_story_cfg_keeps_only_generic_runtime_keys():
    story_id = all_stories()[0]["id"]
    story = load_story(story_id)
    assert story is not None

    cfg = chat_mod._canonicalize_story_cfg(story)

    assert "id" in cfg
    assert "characters" in cfg
    assert "epistemic_seed" in cfg
    assert "world" in cfg
    assert "relationships" in cfg
    assert "setting" not in cfg
    assert "victim" not in cfg
    assert "style" not in cfg
    assert "world_context" not in cfg


def test_noncanonical_story_details_are_seeded_to_transient_buffer():
    story_id = all_stories()[0]["id"]
    story = load_story(story_id)
    assert story is not None

    st = init_state()
    st.story = story_id
    st.user_id = "default_user"
    st.instance = 1

    chat_mod._seed_noncanonical_story_details_to_transient(story, st)

    texts = [e.text for e in st.transient_entries]
    assert texts, "Expected non-canonical story details to be seeded into transient context"
    assert any(t.startswith("story.") or t.startswith("character.") for t in texts)


def test_seed_epistemic_common_knowledge_maps_to_all_characters():
    st = init_state()
    cfg = {
        "epistemic_seed": {
            "canonical_facts": [
                {
                    "id": "f_common",
                    "text": "This fact is common knowledge.",
                    "common_knowledge": True,
                    "confidence": 1.0,
                }
            ]
        }
    }

    chat_mod._seed_epistemic_from_story(cfg, st)

    assert len(st.canonical_facts) == 1
    assert st.canonical_facts[0].known_by == ["all_characters"]


def test_seed_epistemic_claim_visibility_metadata_is_preserved():
    st = init_state()
    cfg = {
        "epistemic_seed": {
            "belief_seeds": {
                "iu": [
                    {
                        "text": "I might know this detail.",
                        "known_by": ["iu"],
                        "not_known_by": ["player"],
                        "maybe_known_by": ["park_so_jin"],
                        "confidence": 0.7,
                    }
                ]
            }
        }
    }

    chat_mod._seed_epistemic_from_story(cfg, st)

    iu_claims = st.get_belief_state("iu").claims
    assert len(iu_claims) == 1
    assert iu_claims[0].known_by == ["iu"]
    assert iu_claims[0].not_known_by == ["player"]
    assert iu_claims[0].maybe_known_by == ["park_so_jin"]
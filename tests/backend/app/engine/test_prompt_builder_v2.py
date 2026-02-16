# tests/backend/app/engine/test_prompt_builder_v2.py
"""Tests for prompt_builder_v2 — contract-driven prompt construction."""
import pytest

from backend.app.engine.story_schema_v2 import StoryPackageV2
from backend.app.engine.turn_contract import build_contract
from backend.app.engine.prompt_builder_v2 import build_system_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _test_pkg() -> StoryPackageV2:
    return StoryPackageV2.from_dict({
        "story_id": "test",
        "version": 2,
        "game": {
            "output_policy": {"narration_style": "cinematic"},
        },
        "knowledge": {
            "chunks": {
                "anchor_identity": {
                    "type": "IDENTITY",
                    "canon_tier": "ANCHOR",
                    "access": {"inject_every_turn": True},
                    "content": {"text": "You are IU. You are a ghost.", "entities": ["IU"]},
                    "tags": ["female"],
                },
                "known_fact": {
                    "type": "FACT",
                    "canon_tier": "CANON",
                    "content": {"text": "You died in this apartment."},
                },
                "secret_killer": {
                    "type": "FACT",
                    "canon_tier": "SECRET_CANON",
                    "access": {"visibility": "RESTRICTED"},
                    "content": {"text": "Manager-nim ordered the killing."},
                },
            },
        },
        "characters": {
            "iu": {
                "identity": {"display_name": "IU", "archetype": "ghost", "tags": ["female"]},
                "traits": {"tone": "melancholy", "speech_style": "poetic"},
                "motivation": {
                    "primary": "Find peace",
                    "fears": ["being forgotten"],
                    "needs": ["closure"],
                },
                "anchors": {"anchor_chunk_ids": ["anchor_identity"]},
                "epistemic": {
                    "known_chunk_ids": ["known_fact"],
                    "believed_chunk_ids": [],
                },
            },
        },
        "relationships": {
            "edges": [
                {"id": "e1", "from": "iu", "to": "iu", "type": "OTHER", "state": {"trust": 0.5}},
            ],
        },
        "world": {
            "locations": {
                "bedroom": {
                    "name": "IU's Bedroom",
                    "description": "A small, dimly lit room with memories.",
                    "speaker_character_ids": ["iu"],
                },
            },
        },
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_prompt_contains_character_name():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "IU" in prompt


def test_prompt_contains_anchors_section():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "IDENTITY ANCHORS" in prompt
    assert "You are IU. You are a ghost." in prompt


def test_prompt_contains_known_facts():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "KNOWN FACTS" in prompt
    assert "You died in this apartment." in prompt


def test_prompt_contains_forbidden_secrets():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "SECRETS YOU MUST NOT REVEAL" in prompt
    assert "Manager-nim ordered the killing." in prompt


def test_prompt_contains_output_style():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "OUTPUT STYLE" in prompt
    assert "cinematic narration" in prompt


def test_prompt_contains_no_player_speech_rule():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "NEVER SPEAK AS THE PLAYER" in prompt


def test_prompt_contains_speaker_labels_rule():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "SPEAKER LABELS" in prompt


def test_prompt_contains_state_tag_requirement():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "[[STATE]]" in prompt


def test_prompt_contains_character_traits():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg)
    assert "melancholy" in prompt
    assert "Find peace" in prompt


def test_prompt_contains_scene_context():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu", location_id="bedroom", world_minute=30)
    prompt = build_system_prompt(contract, pkg, emotion="wistful")
    assert "IU's Bedroom" in prompt
    assert "wistful" in prompt


def test_prompt_player_name_in_speaker_labels():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg, player_name="Chris")
    assert "Chris" in prompt
    assert "NEVER label dialogue with the player's name" in prompt


def test_truth_mode_overrides_narrative():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg, truth_mode=True)
    assert "TRUTH MODE" in prompt
    assert "factual database query interface" in prompt
    # Should NOT have cinematic narration in truth mode
    # (output policy section is empty in truth mode)


def test_truth_mode_omits_player_speech_rules():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg, truth_mode=True)
    # Truth mode skips player speech rules (not relevant for debug)
    assert "NEVER SPEAK AS THE PLAYER" not in prompt


def test_truth_mode_still_has_anchors():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    prompt = build_system_prompt(contract, pkg, truth_mode=True)
    assert "IDENTITY ANCHORS" in prompt
    assert "You are IU" in prompt

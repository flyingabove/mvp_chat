# tests/backend/app/engine/test_turn_contract.py
"""Obsolete v2 tests disabled after production simplification."""

import pytest

pytest.skip("turn contract v2 path removed from active product design", allow_module_level=True)

from backend.app.engine.story_schema_v2 import (
    CanonTier,
    ChunkType,
    StoryPackageV2,
)
from backend.app.engine.turn_contract import (
    TurnContract,
    build_contract,
    evaluate_triggers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _test_pkg() -> StoryPackageV2:
    return StoryPackageV2.from_dict({
        "story_id": "test",
        "version": 2,
        "knowledge": {
            "chunks": {
                "anchor_identity": {
                    "type": "IDENTITY",
                    "canon_tier": "ANCHOR",
                    "access": {"inject_every_turn": True, "speaker_must_not_deny": True},
                    "content": {"text": "You are IU. You are a ghost.", "entities": ["IU"]},
                    "tags": ["female"],
                },
                "anchor_closet": {
                    "type": "FACT",
                    "canon_tier": "ANCHOR",
                    "access": {"inject_every_turn": True},
                    "content": {"text": "The closet binds you to this apartment."},
                },
                "known_fact": {
                    "type": "FACT",
                    "canon_tier": "CANON",
                    "content": {"text": "You died in this apartment."},
                },
                "believed_rumor": {
                    "type": "RUMOR",
                    "canon_tier": "CLAIM",
                    "content": {"text": "Someone else was here that night."},
                },
                "secret_killer": {
                    "type": "FACT",
                    "canon_tier": "SECRET_CANON",
                    "access": {"visibility": "RESTRICTED"},
                    "content": {"text": "Manager-nim ordered the killing."},
                },
                "trigger_memory": {
                    "type": "MEMORY",
                    "canon_tier": "CANON",
                    "content": {"text": "You remember hiding in the closet."},
                },
                "inject_rule": {
                    "type": "RULE",
                    "canon_tier": "CANON",
                    "access": {"inject_every_turn": True, "visibility": "PUBLIC"},
                    "content": {"text": "Always speak softly."},
                },
            },
        },
        "characters": {
            "iu": {
                "identity": {"display_name": "IU", "archetype": "ghost", "tags": ["female"]},
                "anchors": {"anchor_chunk_ids": ["anchor_identity", "anchor_closet"]},
                "epistemic": {
                    "known_chunk_ids": ["known_fact"],
                    "believed_chunk_ids": ["believed_rumor"],
                    "forgotten_chunk_ids": ["trigger_memory"],
                    "memory_rules": {
                        "triggers": [
                            {
                                "id": "closet_trigger",
                                "condition": "mentions:closet",
                                "unlock_chunk_ids": ["trigger_memory"],
                                "probability": 1.0,
                            },
                        ],
                    },
                },
            },
        },
    })


# ---------------------------------------------------------------------------
# build_contract tests
# ---------------------------------------------------------------------------

def test_contract_injects_anchors():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    anchor_ids = {a.id for a in contract.injected_anchors}
    assert "anchor_identity" in anchor_ids
    assert "anchor_closet" in anchor_ids


def test_contract_injects_every_turn_chunks():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    injected_ids = {a.id for a in contract.injected_anchors}
    # inject_rule has inject_every_turn=True, PUBLIC visibility
    assert "inject_rule" in injected_ids


def test_contract_allowed_knowledge():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    allowed_ids = {c.id for c in contract.allowed_knowledge}
    assert "known_fact" in allowed_ids
    assert "believed_rumor" in allowed_ids


def test_contract_forbidden_includes_locked_secret():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    forbidden_ids = {c.id for c in contract.forbidden_knowledge}
    assert "secret_killer" in forbidden_ids


def test_contract_invariants_for_anchors():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    inv_types = [i.type for i in contract.invariants]
    assert "ANCHOR_CONTRADICTION" in inv_types


def test_contract_identity_drift_invariant():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    inv_types = [i.type for i in contract.invariants]
    assert "SPEAKER_IDENTITY_DRIFT" in inv_types


def test_contract_unknown_speaker_returns_empty():
    pkg = _test_pkg()
    contract = build_contract(pkg, "nonexistent")
    assert contract.injected_anchors == []
    assert contract.allowed_knowledge == []


def test_contract_output_policy_inherited():
    pkg = _test_pkg()
    contract = build_contract(pkg, "iu")
    assert contract.output_policy.narration_style == "cinematic"


# ---------------------------------------------------------------------------
# evaluate_triggers tests
# ---------------------------------------------------------------------------

def test_trigger_mentions_unlocks_chunk():
    pkg = _test_pkg()
    unlocked = evaluate_triggers(
        pkg, "iu",
        player_message="What about the closet?",
        seed=42,
    )
    assert "trigger_memory" in unlocked
    assert "trigger_memory" in pkg.characters["iu"].epistemic.known_chunk_ids
    assert "trigger_memory" not in pkg.characters["iu"].epistemic.forgotten_chunk_ids


def test_trigger_no_match():
    pkg = _test_pkg()
    unlocked = evaluate_triggers(
        pkg, "iu",
        player_message="Tell me about the weather",
        seed=42,
    )
    assert unlocked == []
    assert "trigger_memory" in pkg.characters["iu"].epistemic.forgotten_chunk_ids


def test_trigger_already_known_not_duplicated():
    pkg = _test_pkg()
    # First trigger fires
    evaluate_triggers(pkg, "iu", player_message="the closet", seed=42)
    # Second trigger — should not re-add
    unlocked = evaluate_triggers(pkg, "iu", player_message="the closet again", seed=42)
    assert unlocked == []
    assert pkg.characters["iu"].epistemic.known_chunk_ids.count("trigger_memory") == 1


def test_trigger_probability_zero_never_fires():
    pkg = _test_pkg()
    # Override probability to 0
    triggers = pkg.characters["iu"].epistemic.memory_rules.triggers
    # MemoryTrigger is frozen, so we rebuild the pkg with probability=0
    pkg2 = StoryPackageV2.from_dict({
        "story_id": "test",
        "version": 2,
        "knowledge": {
            "chunks": {
                "trigger_memory": {
                    "type": "MEMORY",
                    "canon_tier": "CANON",
                    "content": {"text": "Memory."},
                },
            },
        },
        "characters": {
            "iu": {
                "identity": {"display_name": "IU"},
                "epistemic": {
                    "forgotten_chunk_ids": ["trigger_memory"],
                    "memory_rules": {
                        "triggers": [
                            {
                                "id": "t1",
                                "condition": "mentions:closet",
                                "unlock_chunk_ids": ["trigger_memory"],
                                "probability": 0.0,
                            },
                        ],
                    },
                },
            },
        },
    })
    unlocked = evaluate_triggers(pkg2, "iu", player_message="closet", seed=42)
    assert unlocked == []


def test_trigger_location_condition():
    pkg = StoryPackageV2.from_dict({
        "story_id": "t",
        "version": 2,
        "knowledge": {"chunks": {
            "mem": {"type": "MEMORY", "canon_tier": "CANON", "content": {"text": "M"}},
        }},
        "characters": {
            "iu": {
                "identity": {"display_name": "IU"},
                "epistemic": {
                    "forgotten_chunk_ids": ["mem"],
                    "memory_rules": {"triggers": [
                        {"id": "t1", "condition": "location:room_a", "unlock_chunk_ids": ["mem"]},
                    ]},
                },
            },
        },
    })
    unlocked = evaluate_triggers(pkg, "iu", location_id="room_a", seed=1)
    assert "mem" in unlocked


def test_trigger_minute_gte_condition():
    pkg = StoryPackageV2.from_dict({
        "story_id": "t",
        "version": 2,
        "knowledge": {"chunks": {
            "mem": {"type": "MEMORY", "canon_tier": "CANON", "content": {"text": "M"}},
        }},
        "characters": {
            "iu": {
                "identity": {"display_name": "IU"},
                "epistemic": {
                    "forgotten_chunk_ids": ["mem"],
                    "memory_rules": {"triggers": [
                        {"id": "t1", "condition": "minute_gte:60", "unlock_chunk_ids": ["mem"]},
                    ]},
                },
            },
        },
    })
    # Not enough time
    assert evaluate_triggers(pkg, "iu", world_minute=30, seed=1) == []
    # Enough time
    unlocked = evaluate_triggers(pkg, "iu", world_minute=60, seed=1)
    assert "mem" in unlocked


def test_trigger_chunk_known_condition():
    pkg = StoryPackageV2.from_dict({
        "story_id": "t",
        "version": 2,
        "knowledge": {"chunks": {
            "prereq": {"type": "FACT", "canon_tier": "CANON", "content": {"text": "P"}},
            "result": {"type": "MEMORY", "canon_tier": "CANON", "content": {"text": "R"}},
        }},
        "characters": {
            "iu": {
                "identity": {"display_name": "IU"},
                "epistemic": {
                    "known_chunk_ids": ["prereq"],
                    "forgotten_chunk_ids": ["result"],
                    "memory_rules": {"triggers": [
                        {"id": "t1", "condition": "chunk_known:prereq", "unlock_chunk_ids": ["result"]},
                    ]},
                },
            },
        },
    })
    unlocked = evaluate_triggers(pkg, "iu", seed=1)
    assert "result" in unlocked

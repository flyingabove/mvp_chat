# tests/backend/app/engine/test_invariant_validator.py
"""Obsolete v2 tests disabled after production simplification."""

import pytest

pytest.skip("invariant validator v2 path removed from active product design", allow_module_level=True)

from backend.app.engine.story_schema_v2 import (
    AccessPolicy,
    CanonTier,
    ChunkType,
    Content,
    KnowledgeChunk,
    OutputPolicy,
)
from backend.app.engine.turn_contract import Invariant, TurnContract
from backend.app.engine.invariant_validator import validate_response, Violation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _identity_anchor(name: str = "IU", tags: list = None) -> KnowledgeChunk:
    return KnowledgeChunk(
        id="anchor_identity",
        type=ChunkType.IDENTITY,
        canon_tier=CanonTier.ANCHOR,
        access=AccessPolicy(inject_every_turn=True),
        content=Content(text=f"You are {name}. You are a ghost.", entities=[name], aliases=[]),
        tags=tags or ["female"],
    )


def _closet_anchor() -> KnowledgeChunk:
    return KnowledgeChunk(
        id="anchor_closet",
        type=ChunkType.FACT,
        canon_tier=CanonTier.ANCHOR,
        access=AccessPolicy(inject_every_turn=True),
        content=Content(text="The closet binds you to this apartment.", entities=["closet"]),
    )


def _contract_with_anchors(*anchors: KnowledgeChunk) -> TurnContract:
    invariants = []
    has_identity = False
    for a in anchors:
        invariants.append(Invariant(
            type="ANCHOR_CONTRADICTION",
            description=f"Must not contradict: {a.content.text}",
            chunk_id=a.id,
        ))
        if a.type == ChunkType.IDENTITY:
            has_identity = True
    if has_identity:
        invariants.append(Invariant(
            type="SPEAKER_IDENTITY_DRIFT",
            description="Must not refer to self in third person",
        ))
    return TurnContract(
        speaker_character_id="iu",
        injected_anchors=list(anchors),
        output_policy=OutputPolicy(),
        invariants=invariants,
    )


# ---------------------------------------------------------------------------
# ANCHOR_CONTRADICTION tests
# ---------------------------------------------------------------------------

def test_flags_direct_denial_im_not():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(contract, '*"I\'m not IU,"* she whispers.')
    assert any(v.invariant_type == "ANCHOR_CONTRADICTION" for v in violations)


def test_flags_direct_denial_i_am_not():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(contract, "I am not IU.")
    assert any(v.invariant_type == "ANCHOR_CONTRADICTION" for v in violations)


def test_flags_denial_i_was_never():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(contract, "I was never IU, that's not me.")
    assert any(v.invariant_type == "ANCHOR_CONTRADICTION" for v in violations)


def test_flags_denial_not_a_ghost():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(contract, "I'm not a ghost. I'm alive.")
    assert any(v.invariant_type == "ANCHOR_CONTRADICTION" for v in violations)


def test_allows_normal_dialogue():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(
        contract,
        '*The air shimmers.* **"I remember this place... it feels familiar."**',
    )
    anchor_violations = [v for v in violations if v.invariant_type == "ANCHOR_CONTRADICTION"]
    assert anchor_violations == []


def test_allows_i_dont_remember_my_name():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(
        contract,
        '**"I don\'t remember my name..."** *A flicker of confusion crosses her face.*',
    )
    anchor_violations = [v for v in violations if v.invariant_type == "ANCHOR_CONTRADICTION"]
    assert anchor_violations == []


# ---------------------------------------------------------------------------
# SPEAKER_IDENTITY_DRIFT tests
# ---------------------------------------------------------------------------

def test_flags_third_person_she_was_trapped():
    contract = _contract_with_anchors(_identity_anchor())
    text = '*The room grows cold.* **"She was... trapped here. IU, she was trapped."**'
    violations = validate_response(contract, text)
    assert any(v.invariant_type == "SPEAKER_IDENTITY_DRIFT" for v in violations)


def test_flags_her_story():
    contract = _contract_with_anchors(_identity_anchor())
    text = "IU... her story is a sad one. She was so talented."
    violations = validate_response(contract, text)
    assert any(v.invariant_type == "SPEAKER_IDENTITY_DRIFT" for v in violations)


def test_allows_first_person_self_reference():
    contract = _contract_with_anchors(_identity_anchor())
    text = '**"I was trapped here. I remember the closet."**'
    violations = validate_response(contract, text)
    drift_violations = [v for v in violations if v.invariant_type == "SPEAKER_IDENTITY_DRIFT"]
    assert drift_violations == []


def test_allows_third_person_about_others():
    """When talking about OTHER characters, third person is fine."""
    contract = _contract_with_anchors(_identity_anchor())
    text = '**"She was my friend. Manager-nim, she betrayed me."**'
    violations = validate_response(contract, text)
    # "She" near "Manager-nim" should not flag — it's about someone else
    # The name "IU" doesn't appear near "she" here
    drift_violations = [v for v in violations if v.invariant_type == "SPEAKER_IDENTITY_DRIFT"]
    assert drift_violations == []


def test_no_drift_check_without_identity_anchor():
    """If there are no IDENTITY anchors, no drift check should run."""
    contract = _contract_with_anchors(_closet_anchor())
    text = "She was trapped in the closet."
    violations = validate_response(contract, text)
    drift_violations = [v for v in violations if v.invariant_type == "SPEAKER_IDENTITY_DRIFT"]
    assert drift_violations == []


# ---------------------------------------------------------------------------
# Combined tests
# ---------------------------------------------------------------------------

def test_empty_text_no_violations():
    contract = _contract_with_anchors(_identity_anchor())
    violations = validate_response(contract, "")
    assert violations == []


def test_no_invariants_no_violations():
    contract = TurnContract(speaker_character_id="iu", output_policy=OutputPolicy())
    violations = validate_response(contract, "I'm not IU and she was trapped.")
    assert violations == []

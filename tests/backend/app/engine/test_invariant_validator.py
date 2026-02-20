# tests/backend/app/engine/test_invariant_validator.py
"""Invariant validator tests — kept active per no-skip policy."""

from backend.app.engine.invariant_validator import (
    AnchorFact,
    InvariantCheck,
    InvariantContract,
    Violation,
    validate_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _identity_anchor(name: str = "IU", tags: list = None) -> AnchorFact:
    return AnchorFact(
        id="anchor_identity",
        text=f"You are {name}. You are a ghost.",
        entities=[name],
        aliases=[],
        tags=tags or ["female"],
        is_identity=True,
    )


def _closet_anchor() -> AnchorFact:
    return AnchorFact(
        id="anchor_closet",
        text="The closet binds you to this apartment.",
        entities=["closet"],
        is_identity=False,
    )


def _contract_with_anchors(*anchors: AnchorFact) -> InvariantContract:
    checks = []
    has_identity = False
    for a in anchors:
        checks.append(InvariantCheck(
            type="ANCHOR_CONTRADICTION",
            description=f"Must not contradict: {a.text}",
            anchor_id=a.id,
        ))
        if a.is_identity:
            has_identity = True
    if has_identity:
        checks.append(InvariantCheck(
            type="SPEAKER_IDENTITY_DRIFT",
            description="Must not refer to self in third person",
        ))
    return InvariantContract(
        speaker_id="iu",
        anchors=list(anchors),
        checks=checks,
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


def test_no_checks_no_violations():
    contract = InvariantContract(speaker_id="iu")
    violations = validate_response(contract, "I'm not IU and she was trapped.")
    assert violations == []

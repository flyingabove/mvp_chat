"""Pure invariant checks (BL-86/P-04), tested independently of SeasonRunner."""
from __future__ import annotations

from backend.app.engine.world_model.epistemics import observe_event
from backend.app.sim.invariants import check_cast_size, check_no_consent_bypass, check_no_unperceived_knowledge
from tests.backend.app.sim.helpers import build_lifecycle, build_model


def test_cast_size_passes_at_exactly_six() -> None:
    lifecycle = build_lifecycle()
    assert check_cast_size(lifecycle) == []


def test_cast_size_flags_a_short_house() -> None:
    lifecycle = build_lifecycle()
    lifecycle.depart("ava", minute=0, reason="left early")
    violations = check_cast_size(lifecycle)
    assert len(violations) == 1
    assert "5" in violations[0]


def test_unperceived_knowledge_passes_when_observed() -> None:
    model = build_model()
    event = model.world.add_event(0, "living_room", ("ava", "ben"), "@ava and @ben talked", kind="scene")
    observe_event(model.epistemics, "ava", event.id, "participant", event.truth, 0)
    observe_event(model.epistemics, "ben", event.id, "participant", event.truth, 0)
    model.memories.add("ava", event.truth, "witnessed", 0, event_id=event.id)
    model.memories.add("ben", event.truth, "witnessed", 0, event_id=event.id)
    assert check_no_unperceived_knowledge(model) == []


def test_unperceived_knowledge_flags_fake_omniscience() -> None:
    model = build_model()
    event = model.world.add_event(0, "living_room", ("ava", "ben"), "@ava and @ben talked", kind="scene")
    observe_event(model.epistemics, "ava", event.id, "participant", event.truth, 0)
    model.memories.add("ava", event.truth, "witnessed", 0, event_id=event.id)
    # "cleo" was never recorded as perceiving this event, but somehow has a memory of it.
    model.memories.add("cleo", event.truth, "witnessed", 0, event_id=event.id)
    violations = check_no_unperceived_knowledge(model)
    assert len(violations) == 1
    assert "cleo" in violations[0]


def test_consent_bypass_passes_with_no_accepted_events() -> None:
    model = build_model()
    assert check_no_consent_bypass(model) == []


def test_consent_bypass_flags_an_accepted_event_with_no_logged_verdict() -> None:
    model = build_model()
    model.world.add_event(0, "living_room", ("player", "ava"), "@ava accepted @player's confession",
                          kind="confess_accepted", payload={"act": "confess", "target": "ava"})
    violations = check_no_consent_bypass(model)
    assert len(violations) == 1
    assert "ava" in violations[0]


def test_consent_bypass_passes_when_the_decision_log_backs_the_acceptance() -> None:
    model = build_model()
    model.decision_log.append({"act": "confess", "target": "ava", "final": "accept", "turn": 1})
    model.world.add_event(0, "living_room", ("player", "ava"), "@ava accepted @player's confession",
                          kind="confess_accepted", payload={"act": "confess", "target": "ava"})
    assert check_no_consent_bypass(model) == []

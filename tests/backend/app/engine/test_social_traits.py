"""Unit tests for backend/app/engine/social_traits.py (Six Strangers audit
Phase 3 "Social life": the generic evolving-goal/disposition primitive)."""
from backend.app.engine.social_traits import EvolvingTrait


def test_set_initial_seeds_current_and_history():
    trait = EvolvingTrait(kind="goal", subject_id="iu")
    seeded = trait.set_initial("Find out who killed her manager.", minute=10)

    assert seeded is True
    assert trait.current == "Find out who killed her manager."
    assert trait.confidence == 1.0
    assert len(trait.history) == 1
    assert trait.history[0].content == "Find out who killed her manager."
    assert trait.history[0].source == "author"
    assert trait.history[0].timestamp_minute == 10


def test_set_initial_blank_value_is_noop():
    trait = EvolvingTrait(kind="goal", subject_id="iu")
    seeded = trait.set_initial("   ")

    assert seeded is False
    assert trait.current == ""
    assert trait.history == []


def test_propose_change_appends_history_preserves_old_value():
    trait = EvolvingTrait(kind="disposition", subject_id="makoto", target_id="mizuki")
    trait.set_initial("aggressive toward Mizuki", minute=0)

    applied = trait.propose_change(
        "warming up to Mizuki", minute=500, reason="softened after 5 turns of warmth",
        confidence=0.7, entry_id="shift_1",
    )

    assert applied is True
    assert trait.current == "warming up to Mizuki"
    assert len(trait.history) == 2
    # Old value must still be readable - never rewritten.
    assert trait.history[0].content == "aggressive toward Mizuki"
    assert trait.history[1].content == "warming up to Mizuki"
    assert trait.history[1].provenance == "softened after 5 turns of warmth"
    assert trait.history[1].source == "extractor"


def test_propose_change_idempotent_same_entry_id():
    trait = EvolvingTrait(kind="goal", subject_id="iu")
    trait.set_initial("survive the mystery", minute=0)

    first = trait.propose_change("expose the killer", minute=100, reason="r1", confidence=0.6, entry_id="e1")
    snapshot_len = len(trait.history)
    replay = trait.propose_change("something totally different", minute=999, reason="r2", confidence=0.9, entry_id="e1")

    assert first is True
    assert replay is False
    assert len(trait.history) == snapshot_len
    assert trait.current == "expose the killer"


def test_propose_change_noop_when_value_unchanged():
    trait = EvolvingTrait(kind="goal", subject_id="iu")
    trait.set_initial("find the truth", minute=0)

    applied = trait.propose_change("find the truth", minute=50, reason="r", confidence=0.5, entry_id="e2")

    assert applied is False
    assert len(trait.history) == 1


def test_propose_change_noop_when_blank_value():
    trait = EvolvingTrait(kind="goal", subject_id="iu")
    trait.set_initial("find the truth", minute=0)

    applied = trait.propose_change("   ", minute=50, reason="r", confidence=0.5, entry_id="e3")

    assert applied is False
    assert len(trait.history) == 1
    assert trait.current == "find the truth"


def test_propose_change_clamps_confidence():
    trait = EvolvingTrait(kind="goal", subject_id="iu")
    trait.propose_change("x", minute=0, reason="r", confidence=5.0, entry_id="e1")
    assert trait.confidence == 1.0

    trait2 = EvolvingTrait(kind="goal", subject_id="iu")
    trait2.propose_change("y", minute=0, reason="r", confidence=-3.0, entry_id="e1")
    assert trait2.confidence == 0.0


def test_to_dict_from_dict_round_trip_preserves_full_history():
    trait = EvolvingTrait(kind="disposition", subject_id="makoto", target_id="mizuki")
    trait.set_initial("aggressive toward Mizuki", minute=0)
    trait.propose_change("warming up to Mizuki", minute=500, reason="softened", confidence=0.7, entry_id="shift_1")
    trait.propose_change("in love with Mizuki", minute=1200, reason="confessed feelings", confidence=0.85, entry_id="shift_2")

    restored = EvolvingTrait.from_dict(trait.to_dict())

    assert restored.kind == "disposition"
    assert restored.subject_id == "makoto"
    assert restored.target_id == "mizuki"
    assert restored.current == "in love with Mizuki"
    assert restored.confidence == 0.85
    assert len(restored.history) == 3
    assert [h.content for h in restored.history] == [
        "aggressive toward Mizuki", "warming up to Mizuki", "in love with Mizuki",
    ]
    assert restored.history[1].provenance == "softened"
    assert restored.history[2].timestamp_minute == 1200


def test_from_dict_handles_none_and_empty():
    assert EvolvingTrait.from_dict(None).current == ""
    assert EvolvingTrait.from_dict({}).history == []


def test_from_dict_skips_non_dict_history_entries():
    restored = EvolvingTrait.from_dict({
        "kind": "goal", "subject_id": "x", "current": "y", "confidence": 0.5,
        "history": ["not a dict", {"id": "e1", "content": "y"}, 42],
    })
    assert len(restored.history) == 1
    assert restored.history[0].content == "y"

"""Unit tests for TurnExtractor._parse_json's departure_signal handling
(Phase 2 cast-cycling: "a wish or joke is not departure").
"""
import json

from backend.app.engine.extractors.turn_extractor import TurnExtractor


ALLOWED_LOCATIONS = {"front_entry", "living_room"}
ALLOWED_CHARACTERS = {"makoto", "mizuki", "yuki"}


def _parse(departure_signal_obj):
    raw = json.dumps({"departure_signal": departure_signal_obj})
    return TurnExtractor._parse_json(raw, ALLOWED_LOCATIONS, ALLOWED_CHARACTERS)


def test_departure_signal_absent_defaults_to_none():
    out = TurnExtractor._parse_json("{}", ALLOWED_LOCATIONS, ALLOWED_CHARACTERS)
    assert out.departure_signal is None


def test_departure_signal_certainty_none_is_dropped():
    out = _parse({"character_id": "makoto", "certainty": "NONE", "reason": "no topic"})
    assert out.departure_signal is None


def test_departure_signal_wish_is_captured():
    out = _parse({"character_id": "makoto", "certainty": "WISH", "reason": "joked about leaving"})
    assert out.departure_signal is not None
    assert out.departure_signal.character_id == "makoto"
    assert out.departure_signal.certainty == "WISH"
    assert out.departure_signal.reason == "joked about leaving"


def test_departure_signal_decision_is_captured():
    out = _parse({"character_id": "mizuki", "certainty": "DECISION", "reason": "stated intent to move out"})
    assert out.departure_signal is not None
    assert out.departure_signal.character_id == "mizuki"
    assert out.departure_signal.certainty == "DECISION"


def test_departure_signal_unknown_character_is_dropped():
    out = _parse({"character_id": "arman", "certainty": "DECISION", "reason": "not currently active"})
    assert out.departure_signal is None


def test_departure_signal_missing_character_id_is_dropped():
    out = _parse({"certainty": "DECISION", "reason": "no character named"})
    assert out.departure_signal is None


def test_departure_signal_invalid_certainty_defaults_to_none():
    out = _parse({"character_id": "makoto", "certainty": "MAYBE", "reason": "garbage value"})
    assert out.departure_signal is None


def test_departure_signal_lowercases_character_id():
    out = _parse({"character_id": "MAKOTO", "certainty": "DECISION", "reason": "case check"})
    assert out.departure_signal is not None
    assert out.departure_signal.character_id == "makoto"


def test_departure_signal_certainty_case_insensitive():
    out = _parse({"character_id": "makoto", "certainty": "decision", "reason": "lowercase input"})
    assert out.departure_signal is not None
    assert out.departure_signal.certainty == "DECISION"


def test_no_allowed_character_keys_still_requires_a_character_id():
    """When allowed_character_keys is empty (no filtering applied), an empty
    character_id must still be dropped - the signal is meaningless without
    naming who is leaving."""
    raw = json.dumps({"departure_signal": {"character_id": "", "certainty": "DECISION"}})
    out = TurnExtractor._parse_json(raw, ALLOWED_LOCATIONS, set())
    assert out.departure_signal is None


# ============================================================================
# Phase 3 "Social life": behavior_tags (cheap, every turn) and
# social_shift_signal (rare, only when the engine flags a ripe pattern).
# ============================================================================

def _parse_tags(tags):
    raw = json.dumps({"behavior_tags": tags})
    return TurnExtractor._parse_json(raw, ALLOWED_LOCATIONS, ALLOWED_CHARACTERS)


def _parse_shift(shift_obj):
    raw = json.dumps({"social_shift_signal": shift_obj})
    return TurnExtractor._parse_json(raw, ALLOWED_LOCATIONS, ALLOWED_CHARACTERS)


def test_behavior_tags_absent_defaults_to_empty_list():
    out = TurnExtractor._parse_json("{}", ALLOWED_LOCATIONS, ALLOWED_CHARACTERS)
    assert out.behavior_tags == []


def test_behavior_tags_captures_multiple_entries():
    out = _parse_tags([
        {"from_id": "makoto", "to_id": "mizuki", "tag": "aggressive"},
        {"from_id": "player", "to_id": "makoto", "tag": "warm"},
    ])
    assert len(out.behavior_tags) == 2
    assert out.behavior_tags[0].from_id == "makoto"
    assert out.behavior_tags[0].to_id == "mizuki"
    assert out.behavior_tags[0].tag == "aggressive"
    assert out.behavior_tags[1].from_id == "player"


def test_behavior_tags_drops_entry_with_unknown_character():
    out = _parse_tags([{"from_id": "makoto", "to_id": "arman", "tag": "curious"}])
    assert out.behavior_tags == []


def test_behavior_tags_drops_entry_with_missing_tag():
    out = _parse_tags([{"from_id": "makoto", "to_id": "mizuki", "tag": ""}])
    assert out.behavior_tags == []


def test_behavior_tags_truncates_long_tag():
    out = _parse_tags([{"from_id": "makoto", "to_id": "mizuki", "tag": "x" * 100}])
    assert len(out.behavior_tags[0].tag) == 40


def test_social_shift_signal_absent_defaults_to_none():
    out = TurnExtractor._parse_json("{}", ALLOWED_LOCATIONS, ALLOWED_CHARACTERS)
    assert out.social_shift_signal is None


def test_social_shift_signal_certainty_none_is_dropped():
    out = _parse_shift({"certainty": "NONE", "scope": "goal", "subject_id": "makoto"})
    assert out.social_shift_signal is None


def test_social_shift_signal_wish_is_captured_but_not_shift():
    """The false-positive guard, mirroring departure_signal's WISH: a
    momentary outlier is captured for visibility but is distinguishable
    from a genuine SHIFT - callers must check certainty before applying."""
    out = _parse_shift({
        "certainty": "WISH", "scope": "disposition", "subject_id": "makoto",
        "target_id": "mizuki", "new_value": "briefly warmer", "reason": "one nice moment",
    })
    assert out.social_shift_signal is not None
    assert out.social_shift_signal.certainty == "WISH"


def test_social_shift_signal_shift_requires_new_value():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "goal", "subject_id": "makoto", "new_value": "",
    })
    assert out.social_shift_signal is None


def test_social_shift_signal_shift_with_new_value_is_captured():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "goal", "subject_id": "makoto",
        "new_value": "No longer chasing romance - focused on baseball.",
        "reason": "repeated rejection across several turns",
    })
    assert out.social_shift_signal is not None
    assert out.social_shift_signal.certainty == "SHIFT"
    assert out.social_shift_signal.scope == "goal"
    assert out.social_shift_signal.subject_id == "makoto"
    assert out.social_shift_signal.target_id == ""
    assert out.social_shift_signal.new_value == "No longer chasing romance - focused on baseball."


def test_social_shift_signal_invalid_scope_is_dropped():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "personality", "subject_id": "makoto", "new_value": "x",
    })
    assert out.social_shift_signal is None


def test_social_shift_signal_disposition_requires_target_id():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "disposition", "subject_id": "makoto",
        "target_id": "", "new_value": "warming up",
    })
    assert out.social_shift_signal is None


def test_social_shift_signal_disposition_with_target_is_captured():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "disposition", "subject_id": "makoto",
        "target_id": "mizuki", "new_value": "warming up to Mizuki", "reason": "softened over time",
    })
    assert out.social_shift_signal is not None
    assert out.social_shift_signal.target_id == "mizuki"


def test_social_shift_signal_unknown_subject_is_dropped():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "goal", "subject_id": "arman", "new_value": "x",
    })
    assert out.social_shift_signal is None


def test_social_shift_signal_unknown_target_is_dropped():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "disposition", "subject_id": "makoto",
        "target_id": "arman", "new_value": "x",
    })
    assert out.social_shift_signal is None


def test_social_shift_signal_lowercases_ids():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "disposition", "subject_id": "MAKOTO",
        "target_id": "MIZUKI", "new_value": "x",
    })
    assert out.social_shift_signal.subject_id == "makoto"
    assert out.social_shift_signal.target_id == "mizuki"


def test_social_shift_signal_truncates_long_new_value_and_reason():
    out = _parse_shift({
        "certainty": "SHIFT", "scope": "goal", "subject_id": "makoto",
        "new_value": "x" * 300, "reason": "y" * 300,
    })
    assert len(out.social_shift_signal.new_value) == 200
    assert len(out.social_shift_signal.reason) == 200


# ============================================================================
# BL-16 fix: closed, story-authored behavior_tag_vocabulary. Empty
# vocabulary (the default for every pre-existing story) must be byte-for-
# byte identical to the original free-text behavior - covered above. These
# cases cover what changes once a story authors one.
# ============================================================================

VOCAB = {"warm", "evasive", "aggressive"}


def _parse_tags_with_vocab(tags, vocab=VOCAB):
    raw = json.dumps({"behavior_tags": tags})
    return TurnExtractor._parse_json(raw, ALLOWED_LOCATIONS, ALLOWED_CHARACTERS, vocab)


def test_behavior_tag_in_vocabulary_is_kept():
    out = _parse_tags_with_vocab([{"from_id": "makoto", "to_id": "mizuki", "tag": "warm"}])
    assert len(out.behavior_tags) == 1
    assert out.behavior_tags[0].tag == "warm"


def test_behavior_tag_outside_vocabulary_is_dropped():
    """The exact bug BL-16 targets: a synonym the LLM chooses on its own
    (here "friendly", not in VOCAB) must not silently pollute
    recent_behavior_log with a value that will never exact-match anything
    else - it must be dropped, not passed through."""
    out = _parse_tags_with_vocab([{"from_id": "makoto", "to_id": "mizuki", "tag": "friendly"}])
    assert out.behavior_tags == []


def test_behavior_tag_vocabulary_match_is_case_insensitive_but_canonicalizes():
    out = _parse_tags_with_vocab([{"from_id": "makoto", "to_id": "mizuki", "tag": "WARM"}])
    assert out.behavior_tags[0].tag == "warm", "must canonicalize to the vocabulary's own casing"


def test_behavior_tag_vocabulary_mixed_batch_keeps_only_matching():
    out = _parse_tags_with_vocab([
        {"from_id": "makoto", "to_id": "mizuki", "tag": "warm"},
        {"from_id": "player", "to_id": "makoto", "tag": "nonsense_word"},
        {"from_id": "mizuki", "to_id": "player", "tag": "evasive"},
    ])
    tags = {u.tag for u in out.behavior_tags}
    assert tags == {"warm", "evasive"}


def test_behavior_tag_empty_vocabulary_accepts_anything():
    """Regression guard: an empty/unset vocabulary (every story that
    hasn't authored one) must behave exactly like before this fix."""
    out = _parse_tags_with_vocab([{"from_id": "makoto", "to_id": "mizuki", "tag": "any_free_text"}], vocab=set())
    assert out.behavior_tags[0].tag == "any_free_text"

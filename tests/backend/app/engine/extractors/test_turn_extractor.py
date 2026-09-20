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

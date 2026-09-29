"""BL-39 O08: the existing extraction call reports addressed questions and
judges whether the previous reply resolved the open ones."""
import asyncio
import json
from types import SimpleNamespace

from backend.app.engine.extractors.turn_extractor import (
    MAX_QUESTIONS, QuestionAsked, QuestionStatusUpdate, TurnExtractor,
)
from backend.app.llm.protocols import LegacyExtractionRequest

KEYS = {"iu", "mako"}


def test_parses_questions_to_known_characters_only():
    parsed = TurnExtractor._parse_dict({"questions": [
        {"addressee": "IU", "question": " Who  told you? "},
        {"addressee": "stranger", "question": "Hello?"},
        {"addressee": "mako", "question": ""},
        "not a dict",
    ]}, set(), KEYS)
    assert parsed.questions == [QuestionAsked("iu", "Who told you?")]


def test_question_count_is_capped():
    raw = [{"addressee": "iu", "question": f"Q{i}?"} for i in range(MAX_QUESTIONS + 3)]
    assert len(TurnExtractor._parse_dict({"questions": raw}, set(), KEYS).questions) == MAX_QUESTIONS


def test_parses_only_known_statuses():
    parsed = TurnExtractor._parse_dict({"question_status": [
        {"id": "q1", "status": "Answered"},
        {"id": "q2", "status": "unanswered"},
        {"id": "q3", "status": "maybe"},
        {"id": "", "status": "refused"},
    ]}, set(), KEYS)
    assert parsed.question_updates == [QuestionStatusUpdate("q1", "answered"),
                                       QuestionStatusUpdate("q2", "unanswered")]


def test_missing_fields_default_to_empty():
    parsed = TurnExtractor._parse_dict({}, set(), KEYS)
    assert parsed.questions == [] and parsed.question_updates == []


def test_open_questions_are_listed_in_the_extraction_prompt():
    captured = {}

    async def generate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text=json.dumps({}))

    extractor = TurnExtractor.__new__(TurnExtractor)
    extractor.model = "test"
    extractor._legacy_client = SimpleNamespace(generate=generate)
    request = LegacyExtractionRequest(
        user_msg="Well?", world_locations={}, character_key_to_name={"iu": "IU"},
        previous_turn_assistant_reply="IU looks away.",
        open_questions=({"id": "q1", "addressee": "iu", "text": "Who told you about the footage?"},),
    )
    asyncio.run(extractor._call_legacy_raw(request))
    user_content = captured["messages"][-1]["content"]
    assert "OPEN QUESTIONS (id: addressee: question):\n- q1: asked iu: Who told you about the footage?" in user_content
    assert "13) question_status" in captured["system"]


def test_no_open_questions_prints_none():
    captured = {}

    async def generate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text="{}")

    extractor = TurnExtractor.__new__(TurnExtractor)
    extractor.model = "test"
    extractor._legacy_client = SimpleNamespace(generate=generate)
    asyncio.run(extractor._call_legacy_raw(LegacyExtractionRequest(
        user_msg="hi", world_locations={}, character_key_to_name={})))
    assert "OPEN QUESTIONS (id: addressee: question):\n- none" in captured["messages"][-1]["content"]

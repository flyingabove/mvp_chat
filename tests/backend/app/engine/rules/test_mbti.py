from backend.app.engine.rules.mbti import GLOSS, gloss, normalize


def test_normalize_uppercases_valid_code():
    assert normalize("entp") == "ENTP"


def test_normalize_rejects_invalid_code():
    assert normalize("ABCD") == ""
    assert normalize("") == ""
    assert normalize(None) == ""


def test_gloss_returns_text_for_every_valid_type():
    for code in GLOSS:
        assert gloss(code), f"{code} has no gloss text"


def test_gloss_is_case_insensitive_and_strips_whitespace():
    assert gloss(" entp ") == gloss("ENTP")


def test_gloss_unknown_code_returns_empty_string():
    assert gloss("nope") == ""


def test_all_sixteen_types_covered():
    assert len(GLOSS) == 16

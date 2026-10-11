"""BL-47: a speaker replaying a line they said many turns ago (live beta 2026-09-29: two residents repeated their
arrival introductions word for word when greeted). The old filter only compared against the last three messages."""
from backend.app.engine.dialogue import (OWN_REPEAT_MIN_WORDS, drop_own_repeated_lines, own_repeat_indexes)

INTRO = "Hello, I'm Yuriko. It is good to finally meet the people I'll be living with."


def _line(speaker, text):
    return {"kind": "dialogue", "speaker_id": speaker, "text": text}


def _narration(text):
    return {"kind": "narration", "text": text}


def test_a_speaker_repeating_their_own_earlier_line_is_found():
    segments = [_narration("The room quiets."), _line("yuriko", INTRO), _line("yuriko", "Nice to meet you, Paul.")]
    assert own_repeat_indexes(segments, {"yuriko": [INTRO]}) == [1]


def test_case_punctuation_and_curly_apostrophes_do_not_hide_a_replay():
    replay = "HELLO, I’m Yuriko... it is good to finally meet the people I’ll be living with!"
    assert own_repeat_indexes([_line("yuriko", replay)], {"yuriko": [INTRO]}) == [0]


def test_only_the_same_speakers_history_counts():
    assert own_repeat_indexes([_line("hikaru", INTRO)], {"yuriko": [INTRO]}) == []
    assert own_repeat_indexes([_line("yuriko", INTRO)], {}) == []
    assert own_repeat_indexes([_line(None, INTRO)], {"yuriko": [INTRO]}) == []


def test_short_lines_are_never_treated_as_replays():
    """Everyone says "Thank you, Paul." twice; only a longer, distinctive line is a replay."""
    short = "Goodnight, Paul-kun. Sleep well!"
    assert len(short.split()) < OWN_REPEAT_MIN_WORDS
    assert own_repeat_indexes([_line("minori", short)], {"minori": [short]}) == []


def test_narration_is_never_checked_here():
    assert own_repeat_indexes([_narration(INTRO)], {"yuriko": [INTRO]}) == []


def test_a_new_line_or_a_line_that_merely_shares_words_is_kept():
    same_start = "Hello, I'm Yuriko. It is good to see everyone settling in so quickly tonight."
    assert own_repeat_indexes([_line("yuriko", same_start)], {"yuriko": [INTRO]}) == []


def test_a_line_remembered_truncated_still_matches_by_its_beginning():
    """World-model memories keep only the first 240 characters of a line."""
    long_line = ("I really do want to take my time getting to know everyone here before I decide anything about "
                 "anybody, because this all feels very new and I would rather not rush into things that matter. ") * 2
    remembered = long_line[:240]
    assert own_repeat_indexes([_line("minori", long_line)], {"minori": [remembered]}) == [0]
    assert own_repeat_indexes([_line("minori", "A completely different long line that shares nothing with it at all.")],
                              {"minori": [remembered]}) == []


def test_replays_are_dropped_and_everything_else_is_kept_in_order():
    segments = [_narration("She smiles."), _line("yuriko", INTRO), _line("minori", "That sounds like a lovely plan to me."),
                _line("yuriko", "Shall we sit by the window and talk?")]
    kept = drop_own_repeated_lines(segments, {"yuriko": [INTRO]})
    assert kept == [segments[0], segments[2], segments[3]]


def test_a_reply_made_only_of_replays_is_kept_rather_than_emptied():
    segments = [_line("yuriko", INTRO)]
    assert drop_own_repeated_lines(segments, {"yuriko": [INTRO]}) == segments


def test_a_reply_whose_only_other_content_is_narration_still_drops_the_replay():
    segments = [_narration("The room hums."), _line("yuriko", INTRO)]
    assert drop_own_repeated_lines(segments, {"yuriko": [INTRO]}) == [segments[0]]

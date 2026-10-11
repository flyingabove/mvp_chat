import pytest

from backend.app.engine.content_validation import ContentIssue, find_text_defects
from backend.app.engine.story_loader import build_story_registry, get_active_story_ids

BS = "\\"


def test_reports_literal_escaped_newline_with_field_path():
    story = {"opening": {"text": f"cold..{BS}n{BS}nYou moved in."}}
    assert find_text_defects(story) == [ContentIssue("opening.text", "literal_escaped_newline", 2)]


def test_reports_tabs_and_replacement_characters_inside_lists():
    story = {"characters": [{"voice": f"a{BS}tb"}, {"bio": "it�s"}]}
    assert find_text_defects(story) == [
        ContentIssue("characters[0].voice", "literal_escaped_tab", 1),
        ContentIssue("characters[1].bio", "replacement_character", 1),
    ]


def test_real_newlines_and_typographic_characters_are_clean():
    story = {"opening": {"text": "it’s cold—really.\n\nCafé “quiet”."}}
    assert find_text_defects(story) == []


def test_issue_message_names_path_and_kind():
    assert ContentIssue("opening.text", "literal_escaped_newline", 20).message() == (
        "opening.text: 20 x literal_escaped_newline"
    )


@pytest.mark.parametrize("story_id", get_active_story_ids())
def test_active_stories_have_no_text_decoding_defects(story_id):
    entry = build_story_registry()[story_id]
    issues = find_text_defects(entry["raw"])
    assert not issues, [issue.message() for issue in issues]

"""
Regression coverage for the chat top-bar interactions:
1. Tapping back must leave the chat screen directly, with no "your progress
   is saved" confirm popup in the way.
2. Tapping the game name/avatar in the top-left (#chat-char-name-wrap) must
   offer a "Start New Game" confirm flow that calls launchChat() again,
   leaving the previous session saved and resumable from My Games.

There is no JS test harness in this repo, so this is a structural/string-level
guard on frontend/index.html rather than a real browser test (see
tests/frontend/test_beta_api_base.py for the established pattern).
"""
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _read_index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _extract_listener(html: str, selector_id: str) -> str:
    marker = '$("%s").addEventListener("click", function(){' % selector_id
    start = html.index(marker)
    end = html.index("\n});", start)
    return html[start:end]


def test_back_button_has_no_confirm_popup():
    html = _read_index_html()
    back_handler = _extract_listener(html, "chat-back-btn")

    assert "showConfirm" not in back_handler, (
        "chat-back-btn must navigate straight to the games screen with no "
        "confirm popup — the 'Your progress is saved' dialog was "
        "intentionally removed from the back tap."
    )
    assert 'showScreen("games")' in back_handler


def test_chat_name_wrap_offers_start_new_game():
    html = _read_index_html()
    handler = _extract_listener(html, "chat-char-name-wrap")

    assert "showConfirm" in handler, (
        "Tapping the game name/avatar in the top-left must prompt for "
        "confirmation before starting a new game."
    )
    assert "Start New Game" in handler
    assert "launchChat(" in handler, (
        "Confirming must start a genuinely fresh session via launchChat(), "
        "not mutate the current one in place."
    )


def test_chat_name_wrap_is_visually_clickable():
    html = _read_index_html()
    start = html.index("#chat-char-name-wrap {")
    end = html.index("}", start)
    rule_body = html[start:end]

    assert "cursor: pointer;" in rule_body

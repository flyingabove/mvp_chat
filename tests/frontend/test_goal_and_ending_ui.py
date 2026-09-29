"""BL-39 phase A: the chat screen shows the story goal and a structured ending.

Structural guard on frontend/index.html (the real behaviour is exercised by
scripts/verify_ending_ui_browser.py in Chromium and WebKit).
"""
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _function(html: str, name: str) -> str:
    start = html.index(f"function {name}(")
    return html[start:html.index("\n}\n", start)]


def test_goal_pill_exists_and_is_hidden_until_a_goal_arrives():
    html = _html()
    assert '<button id="chat-goal-pill" type="button" hidden aria-expanded="false">' in html
    body = _function(html, "renderGoal")
    assert "pill.hidden = true" in body and "pill.hidden = false" in body


def test_chat_responses_render_goal_and_ending_payloads():
    send = _function(_html(), "sendMessage")
    assert "renderGoal(data.goal)" in send
    assert "renderEnding(data.ending)" in send
    assert "if (appState.gameEnded && !isInit) return;" in send


def test_ending_card_escapes_text_appears_once_and_locks_input():
    body = _function(_html(), "renderEnding")
    assert 'msgs.querySelector(".ending-card")' in body
    for field in ("ending.label", "ending.title", "ending.summary"):
        assert f"escapeHTML({field}" in body
    assert "if (ending.ends_run) setChatEnded(true);" in body


def test_new_and_resumed_games_reset_and_restore_the_state():
    html = _html()
    launch = _function(html, "launchChat")
    assert "renderGoal(null);" in launch and "setChatEnded(false);" in launch
    resume = _function(html, "resumeGameFromSession")
    assert "renderGoal(sess.goal || null);" in resume
    assert "renderEnding(data.ending || sess.ending);" in resume

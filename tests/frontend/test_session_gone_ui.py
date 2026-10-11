"""BL-44: resuming a saved game the server no longer has must say so, not leave a blank or misleading chat.

Structural guard on frontend/index.html; the real behaviour is checked in Chromium and iPhone WebKit.
"""
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _function(html: str, name: str) -> str:
    start = html.index(f"function {name}(")
    return html[start:html.index("\n}\n", start)]


def test_resume_treats_a_404_history_as_a_gone_session_and_keeps_the_other_paths():
    resume = _function(_html(), "resumeGameFromSession")
    fetch_block = resume[resume.index("/history?limit=20"):]
    assert "r.status === 404" in fetch_block and "handleSessionGone(sess, story)" in fetch_block
    assert "handleUnauthorized()" in fetch_block, "401 keeps its own path"
    assert "History unavailable" in fetch_block, "network/5xx errors keep the soft message"
    assert fetch_block.index("r.status === 404") < fetch_block.index("return r.json()")


def test_a_gone_session_removes_only_that_local_record_and_offers_a_way_forward():
    gone = _function(_html(), "handleSessionGone")
    assert "s.session_id !== id" in gone and "saveSessionsList(" in gone
    assert "BRIEFING_SEEN_KEY" in gone, "the briefing-seen entry goes with it"
    assert "Start new game" in gone and "startGame(story)" in gone
    assert "Back to home" in gone and 'showScreen("home")' in gone
    assert "setChatEnded(true)" in gone and "This saved game is gone" in gone
    assert "refreshSessionCacheFromServer()" in gone
    assert "textContent" in gone and "innerHTML = " not in gone.replace('innerHTML = ""', ""), "no HTML injection"


def test_the_soft_error_path_never_deletes_anything():
    resume = _function(_html(), "resumeGameFromSession")
    catch_block = resume[resume.rindex(".catch(function(){"):]
    assert "handleSessionGone" not in catch_block and "saveSessionsList" not in catch_block


def test_a_gone_session_shows_no_map_and_no_briefing():
    resume = _function(_html(), "resumeGameFromSession")
    assert "appState.session !== sess" in resume[:resume.index("/history?limit=20")],         "the inline map is skipped once the session is gone"
    gone = _function(_html(), "handleSessionGone")
    assert "appState.session = null" in gone

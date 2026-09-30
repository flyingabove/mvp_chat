"""BL-49 briefing screen and BL-46 choice cards: structural guards on frontend/index.html.

The real behaviour is exercised in Chromium and iPhone-sized WebKit (Playwright) before shipping; these keep the
wiring from silently breaking.
"""
import re
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _function(html: str, name: str) -> str:
    start = html.index(f"function {name}(")
    return html[start:html.index("\n}\n", start)]


def test_the_briefing_screen_has_goal_controls_and_map_tabs_and_a_start_button():
    html = _html()
    modal = html[html.index('id="modal-briefing"'):html.index("Onboarding modal (persona")]
    for tab in ("goal", "controls", "map"):
        assert f'data-tab="{tab}"' in modal and f'data-panel="{tab}"' in modal
    assert 'id="briefing-start-btn"' in modal and 'id="briefing-skip-btn"' in modal


def test_a_new_game_goes_through_the_briefing_before_the_first_scene():
    html = _html()
    cont = html[html.index('$("onboard-continue-btn").addEventListener("click"'):html.index("/* ─── BRIEFING (BL-49)")]
    assert "openBriefing(meta, \"start\"" in cont and "launchChat(story, name, gender, guest)" in cont
    assert "launchChat(appState.pendingStory" not in cont, "launchChat must only run after the briefing"
    opener = _function(html, "openBriefing")
    assert "if (onStart) onStart(); return;" in opener, "a missing briefing never blocks play"
    assert 'textContent' in opener and "innerHTML = t" not in opener, "briefing text is never injected as HTML"


def test_skipped_or_not_the_chat_still_prints_the_goal_and_the_two_basic_controls():
    html = _html()
    card = _function(html, "addHowToPlayCard")
    assert '"Goal: " + b.goal' in card and "slice(1, 3)" in card
    launch = _function(html, "launchChat")
    assert "addHowToPlayCard(appState.pendingMeta)" in launch and "markBriefingSeen(session.session_id)" in launch


def test_games_started_before_the_briefing_show_it_once_on_resume():
    html = _html()
    helper = _function(html, "showLegacyBriefingOnce")
    assert "briefingSeen(sess.session_id)" in helper and "markBriefingSeen(sess.session_id)" in helper
    assert 'openBriefing(meta, "view")' in helper
    assert "appState.session !== sess" in helper, "never after the player has left or the game turned out to be gone"
    resume = _function(html, "resumeGameFromSession")
    assert resume.count("showLegacyBriefingOnce(sess, story)") == 2, "after history loads, and on the offline path"
    fetch_block = resume[resume.index("/history?limit=20"):]
    assert fetch_block.index("r.status === 404") < fetch_block.index("showLegacyBriefingOnce"),         "a gone game never pops the briefing over its own message"


def test_the_menu_has_how_to_play_and_map_has_a_slash_alias():
    html = _html()
    assert 'id="dd-howto"' in html and '$("dd-howto").addEventListener' in html
    send = _function(html, "sendMessage")
    assert r"\/map" in send and "showMapModal(true)" in send


def test_chat_responses_render_the_pending_choice_and_resume_restores_it():
    html = _html()
    send = _function(html, "sendMessage")
    assert "renderChoiceCard(data && data.pending_choice)" in send
    resume = _function(html, "resumeGameFromSession")
    assert "renderChoiceCard(data.pending_choice)" in resume


def test_choice_cards_answer_with_a_normal_message_and_never_inject_html():
    html = _html()
    answer = _function(html, "answerChoiceCard")
    assert '"__choice__:" + choice.id + ":" + optionId' in answer and "suppressUserMessage: true" in answer
    card = _function(html, "renderChoiceCard")
    assert ".textContent = choice.prompt" in card and ".textContent = opt.label" in card
    assert not re.search(r"innerHTML\s*=\s*[^;]*(choice\.prompt|opt\.label)", card)
    assert "if (i > 0)" in card, "the second option is always 'not now' and is handled locally"
    ending = _function(html, "renderEnding")
    assert "clearChoiceCard();" in ending, "an ending removes any open card"

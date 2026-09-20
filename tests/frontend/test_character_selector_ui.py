from pathlib import Path


INDEX_PATH = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def test_character_selector_is_one_step_and_card_based():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert 'class="persona-grid"' in html
    assert html.count('data-mode="default"') == 1
    assert html.count('data-mode="create"') == 1
    assert "Continue as Paul" in html
    assert 'appState.onboardStep = "character"' in html
    assert 'appState.onboardStep = "gender"' not in html
    assert "function updateCharacterContinueState()" in html


def test_character_selector_has_mobile_safe_layout_and_accessible_controls():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in html
    assert "env(safe-area-inset-top" in html
    assert "max-height: calc(100dvh" in html
    assert 'role="radiogroup" aria-label="Character choice"' in html
    assert 'role="radio" aria-checked="true"' in html
    assert 'aria-label="Character gender"' in html


def test_default_persona_copy_matches_server_profile():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "Paul Dingus" in html
    assert "Devilishly handsome Black man who knows a little Japanese." in html
    assert 'id="onboard-default-avatar"' in html
    assert 'renderAvatarImage($("onboard-default-avatar")' in html

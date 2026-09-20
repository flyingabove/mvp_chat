"""Structural coverage for the reusable player-facing cast roster UI."""
from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _read_index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_cast_menu_sends_one_shot_command_without_chat_echo():
    html = _read_index_html()

    assert 'id="dd-cast"' in html
    assert 'sendMessage("[CAST]", false, { suppressUserMessage: true, countAsTurn: false });' in html
    assert "if (!isInit && !options.suppressUserMessage)" in html
    assert "options.countAsTurn !== false" in html


def test_cast_roster_renders_only_public_lifecycle_groups():
    html = _read_index_html()
    start = html.index("function renderCastRoster")
    end = html.index("\nfunction showTypingIndicator", start)
    renderer = html[start:end]

    assert "roster.active" in renderer
    assert "roster.vacancies" in renderer
    assert "roster.departed" in renderer
    assert 'labels.active || "Present"' in renderer
    assert 'labels.vacancy || "Room available"' in renderer
    assert 'labels.departed || "Moved out"' in renderer
    assert "roster.queue" not in renderer
    assert "roster.future" not in renderer


def test_chat_response_passes_structured_roster_to_renderer():
    html = _read_index_html()

    assert "if (data && data.cast_roster) renderCastRoster(data.cast_roster);" in html

"""Terrace's studio panel speaks only after the run ends, never as a mid-game aside."""
import json
from pathlib import Path

from backend.app.engine import prompt_builder as pb
from backend.app.engine.state import init_state

STORY = Path(__file__).resolve().parents[4] / "backend/app/stories/7_six_strangers/six_strangers_story.json"


def _terrace_state():
    state = init_state()
    state.story_cfg = json.loads(STORY.read_text(encoding="utf-8"))
    return state


def test_terrace_prompt_carries_no_mid_game_panel_aside():
    text = pb._mode_context_section(_terrace_state())
    assert text, "Terrace still renders its mode context"
    assert "Narrator aside device" not in text, "the panel must not comment during play"


def test_the_panel_finale_is_still_configured():
    cfg = _terrace_state().story_cfg
    assert cfg.get("commentary"), "the end-of-game panel stays"
    assert not (cfg["mode"].get("narrator_asides") or {}).get("enabled")

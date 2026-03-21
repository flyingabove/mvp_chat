
from backend.app.knowledge.runtime import index_service as isvc


def test_default_picks_first_sorted_entry(monkeypatch):
    """First sorted directory should be chosen as default (deterministic ordering)."""
    monkeypatch.setattr(isvc.IndexService, "_list_character_dirs", lambda: ["1_alpha", "2_beta", "3_gamma"])
    monkeypatch.delenv("KNOWLEDGE_CHARACTER_ID", raising=False)
    isvc.IndexService.reset_for_tests()
    # _list_character_dirs returns sorted, so "1_alpha" is first
    assert isvc.IndexService.get_active_character() == "1_alpha"


def test_default_uses_first_when_only_one(monkeypatch):
    monkeypatch.setattr(isvc.IndexService, "_list_character_dirs", lambda: ["2_beta"])
    monkeypatch.delenv("KNOWLEDGE_CHARACTER_ID", raising=False)
    isvc.IndexService.reset_for_tests()
    assert isvc.IndexService.get_active_character() == "2_beta"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_CHARACTER_ID", "env_pick")
    monkeypatch.setattr(isvc.IndexService, "_list_character_dirs", lambda: ["1_alpha", "2_beta"])
    isvc.IndexService.reset_for_tests()
    assert isvc.IndexService.get_active_character() == "env_pick"

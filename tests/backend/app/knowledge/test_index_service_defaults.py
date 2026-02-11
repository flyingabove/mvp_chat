import types

from backend.app.knowledge.runtime import index_service as isvc


def test_default_prefers_1_iu_when_multiple(monkeypatch):
    monkeypatch.setattr(isvc.IndexService, "_list_character_dirs", lambda: ["2_jennie", "1_iu", "3_other"])
    monkeypatch.delenv("KNOWLEDGE_CHARACTER_ID", raising=False)
    isvc.IndexService.reset_for_tests()
    assert isvc.IndexService.get_active_character() == "1_iu"


def test_default_uses_first_when_no_iu(monkeypatch):
    monkeypatch.setattr(isvc.IndexService, "_list_character_dirs", lambda: ["2_jennie", "3_other"])
    monkeypatch.delenv("KNOWLEDGE_CHARACTER_ID", raising=False)
    isvc.IndexService.reset_for_tests()
    assert isvc.IndexService.get_active_character() == "2_jennie"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_CHARACTER_ID", "env_pick")
    monkeypatch.setattr(isvc.IndexService, "_list_character_dirs", lambda: ["1_iu", "2_jennie"])
    isvc.IndexService.reset_for_tests()
    assert isvc.IndexService.get_active_character() == "env_pick"

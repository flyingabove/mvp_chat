from pathlib import Path


INDEX_PATH = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def test_frontend_uses_character_avatar_registry_and_fallbacks():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "CHARACTER_ASSET_MAP" in html
    assert '/img/characters/' in html
    assert '/img/avatars/persona_default.svg' in html
    assert "getCharacterAvatarSrc" in html
    assert "renderCharacterAvatar" in html

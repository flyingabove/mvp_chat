from backend.app.engine.character_assets import (
    DEFAULT_PERSONA_AVATAR,
    resolve_character_avatar_url,
)


def test_character_avatar_lookup_uses_reusable_aliases():
    assert resolve_character_avatar_url("makoto") == "/img/characters/Makoto_Hasegawa.png"
    assert resolve_character_avatar_url(character_name="Mizuki Shida") == "/img/characters/Mizuki_Shida.png"
    assert resolve_character_avatar_url("player") == DEFAULT_PERSONA_AVATAR
    assert resolve_character_avatar_url("persona") == DEFAULT_PERSONA_AVATAR
    assert resolve_character_avatar_url("missing_character") == DEFAULT_PERSONA_AVATAR

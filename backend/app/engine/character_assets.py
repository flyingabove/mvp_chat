"""Reusable asset paths for story characters and persona avatars.

The front-end and the game engine both rely on a small, stable set of portrait
files for NPCs and a generic fallback for the player/persona. The asset paths are
kept server-side here so a future UI or API can reuse the same canonical lookup
without hardcoding naming conventions in multiple places.
"""

from __future__ import annotations

import re
from typing import Iterable

DEFAULT_PERSONA_AVATAR = "/img/avatars/persona_default.svg"
CHARACTER_ASSET_MAP: dict[str, str] = {
    "makoto": "/img/characters/Makoto_Hasegawa.png",
    "minori": "/img/characters/Minori_Nakada.png",
    "yuki": "/img/characters/Yuki_Adachi.png",
    "mizuki": "/img/characters/Mizuki_Shida.png",
    "uchi": "/img/characters/Tatsuya_Uchihara.png",
    "yuriko": "/img/characters/Yuriko_Hayata.png",
    "arman": "/img/characters/Arman_Bitaraf.png",
    "arisa": "/img/characters/Arisa_Ohata.png",
    "hikaru": "/img/characters/Hikaru_Ota.png",
    "natsumi": "/img/characters/Natsumi_Saito.png",
    "misaki": "/img/characters/Misaki_Tamori.png",
    "yuto": "/img/characters/Yuto_Handa.png",
    "riko": "/img/characters/Riko_Nagai.png",
    "momoka": "/img/characters/Momoka_Mitsunaga.png",
    "hayato": "/img/characters/Hayato_Terashima.png",
    "yuuki_byrnes": "/img/characters/Yuuki_Byrnes.png",
    "masako": "/img/characters/Masako_Endo_Martha.png",
    "player": DEFAULT_PERSONA_AVATAR,
    "persona": DEFAULT_PERSONA_AVATAR,
    "default_persona": DEFAULT_PERSONA_AVATAR,
    "six_strangers": "/img/six_strangers_house.jpg",
}


def _normalize_key(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.replace("\"", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text


def resolve_character_avatar_url(character_id: str | None = None, character_name: str | None = None, *, fallback: str = DEFAULT_PERSONA_AVATAR) -> str:
    """Return a stable portrait URL for the given character or persona.

    Character IDs are preferred (e.g. ``makoto``), but story data often only has a
    display name. In that case we normalize the name and look it up with the same
    aliases used in the asset map.
    """
    candidates: Iterable[str] = []
    if character_id:
        candidates = [character_id]
    if character_name:
        candidates = [*candidates, character_name]
    if not candidates:
        return fallback

    for candidate in candidates:
        key = _normalize_key(candidate)
        if key in CHARACTER_ASSET_MAP:
            return CHARACTER_ASSET_MAP[key]

        parts = [part for part in key.split("_") if part]
        for part in parts + list(reversed(parts)):
            if part in CHARACTER_ASSET_MAP:
                return CHARACTER_ASSET_MAP[part]

        if key and key not in {"player", "persona", "default_persona"}:
            maybe = key.replace("_the_", "")
            if maybe in CHARACTER_ASSET_MAP:
                return CHARACTER_ASSET_MAP[maybe]

    return fallback

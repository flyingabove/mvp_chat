"""Build a WorldModel from a GameState (new game or an old save).

Everything story-specific comes from story JSON:
  world_model.enabled            (default true)
  world_model.homes              {character_key: place_id}
  world_model.routines           {templates: {name: {blocks, free_place}}, characters: {key: {template, blocks, home}}}
  world_model.threads            [{id, owner, title, topics, milestones: [...]}]
  world_model.entities           [{id, kind: evidence|object, name, aliases, location, surfaces: [...]}]
A story without these sections still gets locations, memories, speakers and
per-character state; characters simply keep their places (no routines).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from backend.app.engine.world_model.character import CharacterState
from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.memory import MemoryStore
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.routine import Routine, block_key, build_routine
from backend.app.engine.world_model.threads import Thread
from backend.app.engine.world_model.world import World

LORE_CAP = 80


def story_section(state: Any) -> dict[str, Any]:
    cfg = getattr(state, "story_cfg", None) or {}
    if hasattr(cfg, "as_dict"):
        cfg = cfg.as_dict()
    section = cfg.get("world_model") if isinstance(cfg, dict) else None
    return section if isinstance(section, dict) else {}


def enabled_for(state: Any) -> bool:
    return bool(story_section(state).get("enabled", True))


def eligible_ids(state: Any) -> list[str]:
    lifecycle = getattr(state, "cast_lifecycle", None)
    characters = getattr(state, "characters", {}) or {}
    if lifecycle is not None and getattr(lifecycle, "enabled", False):
        return [k for k in characters if k != PLAYER and lifecycle.is_scene_eligible(k)]
    return [k for k in characters if k != PLAYER]


def _descriptor(role: str) -> str:
    first = (role or "").split(",")[0].strip()
    return f"the {first[0].lower()}{first[1:]}" if first else "someone"


def _slot_group(state: Any, cid: str) -> str:
    lifecycle = getattr(state, "cast_lifecycle", None)
    member = (getattr(lifecycle, "members", {}) or {}).get(cid) if lifecycle else None
    return str(getattr(member, "slot_group", "") or "")


def home_for(state: Any, cid: str, fallback: str = "") -> str:
    section = story_section(state)
    homes = section.get("homes") or {}
    if cid in homes:
        return str(homes[cid])
    cfg = getattr(state, "story_cfg", None) or {}
    bedrooms = ((cfg.get("cast_lifecycle") or {}).get("player_bedrooms") or {}) if isinstance(cfg, dict) else {}
    group = _slot_group(state, cid)
    if group and group in bedrooms:
        return str(bedrooms[group])
    starts = ((cfg.get("world") or {}).get("character_start_locations") or {}) if isinstance(cfg, dict) else {}
    return str(starts.get(cid) or fallback)


def make_character(state: Any, cid: str) -> CharacterState:
    source = (getattr(state, "characters", {}) or {})[cid]
    section = story_section(state)
    routines = section.get("routines") or {}
    location = (getattr(state, "character_locations", {}) or {}).get(cid, "")
    home = home_for(state, cid, fallback=location)
    char_cfg = (routines.get("characters") or {}).get(cid) or {}
    home = str(char_cfg.get("home") or home)
    # Only characters the story lists get a routine (default sleep included):
    # an unlisted character - e.g. a ghost bound to one room - never moves.
    routine = build_routine(char_cfg, routines.get("templates") or {}, home) if char_cfg else Routine(home=home)
    # Mood only when authored for this character: Character.emotion defaults to
    # the story's opening emotion, which describes the player's arrival.
    mood = str((section.get("moods") or {}).get(cid) or "")
    return CharacterState(id=cid, name=str(getattr(source, "name", cid) or cid),
                          mood=mood, routine=routine,
                          descriptor=_descriptor(str(getattr(source, "role", "") or "")),
                          slot_group=_slot_group(state, cid))


def lore_owner_for(state: Any) -> str:
    """The character whose authored knowledge bundle the story loads (IU -> 'iu')."""
    bundle = str(getattr(state, "knowledge_character_id", "") or "")
    for cid, character in (getattr(state, "characters", {}) or {}).items():
        if bundle and str(getattr(character, "knowledge_character_id", "") or "") == bundle:
            return cid
    main = (getattr(state, "characters", {}) or {}).get(str(getattr(state, "main_character_id", "") or ""))
    return str(getattr(main, "key", "") or "") if main is not None and getattr(main, "is_main", False) else ""


def settle_into_current_block(model: WorldModel, cid: str) -> None:
    """The staged placement is authoritative at the moment a character enters the
    world: adopt the routine block active now WITHOUT moving them, so routines
    change things only at the next boundary (a chef on shift at 19:00 who was
    staged at home for the opening dinner stays home until his block ends)."""
    character = model.characters[cid]
    character.block = block_key(character.routine.active(model.world, model.world.minute, cid, model.seed))


def _seed_memories(state: Any, store: MemoryStore, lore: Iterable[dict], lore_owner: str) -> None:
    for fact in getattr(state, "canonical_facts", []) or []:
        owners = [k for k in (getattr(fact, "known_by", []) or []) if k not in ("all", "all_characters")]
        text = str(getattr(fact, "text", "") or getattr(fact, "content", "") or "").strip()
        if not text or not owners:
            continue
        for owner in owners:
            store.add(owner, text, "authored", 0, private=len(owners) == 1)
    if lore_owner:
        for chunk in list(lore)[:LORE_CAP]:
            text = str(chunk.get("text") or "").strip()
            if text:
                store.add(lore_owner, text, "authored", 0, kind="lore", private=True)


def _entities(section: dict[str, Any]) -> list[tuple[Entity, str]]:
    found = []
    for raw in section.get("entities") or []:
        entity = Entity(id=str(raw["id"]), kind=str(raw.get("kind") or "evidence"), name=str(raw.get("name") or ""),
                        aliases=list(raw.get("aliases") or []),
                        props={k: v for k, v in raw.items() if k not in ("id", "kind", "name", "aliases", "location")})
        found.append((entity, str(raw.get("location") or "")))
    return found


def build_world_model(state: Any, lore: Optional[Iterable[dict]] = None) -> WorldModel:
    section = story_section(state)
    cfg = getattr(state, "story_cfg", None) or {}
    start = str(getattr(state, "world_start_datetime", "") or ((cfg.get("world") or {}).get("start_datetime", "")
                                                              if isinstance(cfg, dict) else ""))
    world = World(start_datetime=start, minute=int(getattr(state, "minute", 0) or 0))
    model = WorldModel(world=world, seed=f"{getattr(state, 'story', '')}:{getattr(state, 'instance', 1)}:"
                                          f"{getattr(state, 'user_id', '')}:{getattr(state, 'player_name', '')}",
                       player_name=str(getattr(state, "player_name", "") or "the player"))
    world.entities[PLAYER] = Entity(PLAYER, "player", model.player_name)
    if getattr(state, "location_id", ""):
        world.move(PLAYER, state.location_id)
    locations = getattr(state, "character_locations", {}) or {}
    for cid in eligible_ids(state):
        model.characters[cid] = make_character(state, cid)
        world.entities[cid] = Entity(cid, "character", model.characters[cid].name)
        if locations.get(cid):
            world.move(cid, locations[cid])
        settle_into_current_block(model, cid)
    for entity, location in _entities(section):
        world.entities[entity.id] = entity
        if location:
            world.move(entity.id, location)
    model.threads = [Thread.from_dict(t) for t in section.get("threads") or []]
    lore_owner = lore_owner_for(state) if lore else ""
    _seed_memories(state, model.memories, lore or [], lore_owner)
    player_group = getattr(getattr(state, "cast_lifecycle", None), "player_slot_group", "") or ""
    bedrooms = ((cfg.get("cast_lifecycle") or {}).get("player_bedrooms") or {}) if isinstance(cfg, dict) else {}
    model.home_of_player = str(section.get("player_home") or bedrooms.get(player_group) or "")
    return model

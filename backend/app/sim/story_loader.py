"""Build a `SeasonRunner` story from an authored story file, with no player (BL-86, P-06).

The world model comes from the same `bootstrap.build_world_model` a real game uses, so the residents, routines,
homes and place names are the story's own; nothing here knows a story id. Only the headless parts differ: there is
no human, so the roster is chosen from a seed (`choose_initial_roster(rng=...)`, repeatable) and the player's slot
stays reserved, which keeps the cast at the authored size. Relationship changes land in `InMemoryRelationships`
for now (the real character graph is P-10's work).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend.app.engine.cast_lifecycle import CastLifecycleState, CastStatus
from backend.app.engine.state import init_state
from backend.app.engine.story_loader import load_story
from backend.app.engine.world_model import bootstrap
from backend.app.sim.fixtures import InMemoryRelationships
from backend.app.sim.runner import Story


@dataclass(frozen=True)
class CastNote:
    """What a writer may know about one resident: authored facts only."""
    key: str
    name: str
    role: str
    motive: str = ""
    mbti: str = ""


@dataclass
class SeasonSetup:
    story: Story
    cast: dict[str, CastNote]
    title: str = ""
    premise: str = ""
    start: str = ""
    place_names: dict[str, str] = field(default_factory=dict)
    cfg: dict = field(default_factory=dict)          # the story's own JSON (goals, personalities) for writers and the theatre

    def name(self, key: str) -> str:
        note = self.cast.get(key)
        return note.name if note else key

    def place(self, place_id: str) -> str:
        return self.place_names.get(place_id) or place_id.replace("_", " ")

    def clock(self, minute: int) -> str:
        """The wall-clock moment of a world minute, e.g. "Wednesday 18:30" (empty when the story has no start)."""
        try:
            moment = datetime.fromisoformat(self.start) + timedelta(minutes=int(minute))
        except ValueError:
            return ""
        return moment.strftime("%A %H:%M")


def build_season(story_id: str, seed: str, player_gender: str = "F", ai_player_slot: bool = False) -> SeasonSetup:
    """`ai_player_slot`: nobody plays, so the slot a human would hold is filled by one more resident (a full house)."""
    definition = load_story(story_id)
    if definition is None:
        raise ValueError(f"story not found: {story_id}")
    cfg = definition.as_dict()
    state = init_state()
    state.story, state.instance, state.story_cfg = story_id, definition.instance, cfg
    state.gender = "M" if str(player_gender).upper() == "M" else "F"
    state.player_name, state.user_id = "the resident", f"season:{seed}"
    state.characters = {c.key: c for c in definition.characters}
    lifecycle = _lifecycle(cfg, state, seed, ai_player_slot)
    state.cast_lifecycle = lifecycle
    world_cfg = cfg.get("world") or {}
    state.world_start_datetime = str(world_cfg.get("start_datetime") or "")
    state.character_locations = _starts(cfg, lifecycle, state.characters)
    model = bootstrap.build_world_model(state)
    model.seed = f"{story_id}:{seed}"
    notes = _cast(cfg, model.characters)
    return SeasonSetup(
        story=Story(model=model, relationships=InMemoryRelationships(), cast_lifecycle=lifecycle,
                    expected_cast_size=_cast_size(lifecycle, model)),
        cast=notes, title=str(definition.title or story_id), premise=str(cfg.get("description") or ""),
        start=state.world_start_datetime, cfg=cfg,
        place_names={str(k): str(v) for k, v in ((cfg.get("world_model") or {}).get("place_names") or {}).items()})


def _lifecycle(cfg: dict, state, seed: str, ai_player_slot: bool = False):
    config = cfg.get("cast_lifecycle") or {}
    if not config.get("enabled"):
        return None
    lifecycle = CastLifecycleState.from_config(config, character_ids=state.characters.keys())
    group = (config.get("player_slot_groups") or {}).get(state.gender)
    if config.get("randomize_initial_roster") and group:
        lifecycle.choose_initial_roster(group, rng=random.Random(seed))
    if config.get("player_mode") == "resident_slot" and group:
        if ai_player_slot:
            _seat_ai_resident(lifecycle, group)
        else:
            lifecycle.reserve_player_slot(group)
        lifecycle.require_replacement = bool(config.get("require_replacement", False))
    return lifecycle


def _seat_ai_resident(lifecycle, group: str) -> None:
    """Fill the player's slot with the next resident in that slot's queue, so a no-player season has a full house."""
    chosen = lifecycle.next_up(group)
    if chosen is None:
        return
    member = lifecycle.members[chosen]
    member.status, member.activated_minute = CastStatus.ACTIVE, 0
    lifecycle._validate()


def _starts(cfg: dict, lifecycle, characters: dict) -> dict[str, str]:
    """Where each resident is at minute 0: the story's opening gathering place, else their authored start."""
    starts = {str(k): str(v) for k, v in ((cfg.get("world") or {}).get("character_start_locations") or {}).items()}
    gather = str((cfg.get("cast_lifecycle") or {}).get("initial_active_location_id") or "")
    ids = lifecycle.active_ids() if lifecycle is not None else [k for k in characters if k != "player"]
    return {cid: gather or starts.get(cid, "") for cid in ids if gather or starts.get(cid)}


def _cast_size(lifecycle, model) -> int:
    """The authored house size (slot capacities), so the cast invariant fails if a run ever loses or adds a resident."""
    return sum(lifecycle.slot_capacities.values()) if lifecycle is not None else len(model.characters)


def _cast(cfg: dict, present: dict) -> dict[str, CastNote]:
    authored = {str(c.get("key")): c for c in cfg.get("characters") or [] if isinstance(c, dict)}
    mbti = {str(k): str((v or {}).get("mbti") or "") if isinstance(v, dict) else str(v or "")
            for k, v in (cfg.get("personalities") or {}).items()}
    return {cid: CastNote(cid, str(authored.get(cid, {}).get("name") or cid), str(authored.get(cid, {}).get("role") or ""),
                          str(authored.get(cid, {}).get("motive") or ""),
                          str(authored.get(cid, {}).get("mbti") or mbti.get(cid, "")))
            for cid in present}

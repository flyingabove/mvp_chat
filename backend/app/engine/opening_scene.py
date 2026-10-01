"""Engine-backed opening scene: who physically greets the player at game start.

A story may author ``opening.welcome_party`` to decide which NPCs are in the
player's starting location when the game begins::

    "opening": {
      "welcome_party": {"size": 2, "gender": "opposite_player", "exclusive": true}
    }

- ``size``: how many NPCs greet the player (default 2).
- ``gender``: ``any`` | ``opposite_player`` | ``same_as_player`` | ``M`` | ``F``.
  Character gender comes from the authored ``gender`` field ("M"/"F") on each
  character. If too few candidates match, the party is filled from the rest
  so the opening never loses its greeters.
- ``exclusive``: move every other NPC out of the player's start location, so
  the people present are exactly the welcome party (default true).
- ``fallback_location_id``: where displaced NPCs go (default: the story's
  ``cast_lifecycle.initial_active_location_id``). If that is the start room
  itself, nobody is displaced - NPCs are never left without a location.

Staging writes real engine state — ``character_locations``, the focal
``main_character_id`` and ``opening_cast`` — so the opening prose, the SCENE
BRIEF's people-present list and the first storyteller reply all describe the
same room. Stories without ``welcome_party`` keep their previous behavior.
"""
from __future__ import annotations

import random
import re
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional

if TYPE_CHECKING:
    from backend.app.engine.state import GameState

GENDER_RULES = {"any", "opposite_player", "same_as_player", "M", "F"}


@dataclass(frozen=True)
class WelcomePartyRule:
    size: int = 2
    gender: str = "any"
    exclusive: bool = True
    fallback_location_id: str = ""

    @classmethod
    def from_config(cls, cfg: Any) -> Optional["WelcomePartyRule"]:
        """Parse ``opening.welcome_party``; None when the story doesn't author one."""
        if not isinstance(cfg, Mapping):
            return None
        gender = str(cfg.get("gender") or "any").strip()
        if gender.upper() in {"M", "F"}:
            gender = gender.upper()
        if gender not in GENDER_RULES:
            raise ValueError(f"opening.welcome_party.gender must be one of {sorted(GENDER_RULES)}, got {gender!r}")
        size = int(cfg.get("size", 2))
        if size < 1:
            raise ValueError("opening.welcome_party.size must be >= 1")
        return cls(
            size=size,
            gender=gender,
            exclusive=bool(cfg.get("exclusive", True)),
            fallback_location_id=str(cfg.get("fallback_location_id") or "").strip(),
        )

    def wanted_gender(self, player_gender: Optional[str]) -> Optional[str]:
        """The NPC gender this rule prefers for a player, or None for no preference."""
        player = normalize_gender(player_gender)
        if self.gender in {"M", "F"}:
            return self.gender
        if self.gender == "any" or player is None:
            return None
        if self.gender == "same_as_player":
            return player
        return "F" if player == "M" else "M"


def normalize_gender(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if text in {"M", "MALE", "MAN"}:
        return "M"
    if text in {"F", "FEMALE", "WOMAN"}:
        return "F"
    return None


def character_gender(character: Any) -> Optional[str]:
    """Authored gender of a Character ("M"/"F"), stored in its JSON ``gender`` key."""
    if character is None:
        return None
    direct = getattr(character, "gender", None)
    if direct:
        return normalize_gender(direct)
    meta = getattr(character, "meta", None) or {}
    return normalize_gender(meta.get("gender"))


def choose_welcome_party(
    candidates: Iterable[str],
    genders: Mapping[str, Optional[str]],
    player_gender: Optional[str],
    rule: WelcomePartyRule,
    rng: Optional[random.Random] = None,
) -> list[str]:
    """Pick ``rule.size`` greeters, preferring the rule's gender, in random order."""
    rng = rng or secrets.SystemRandom()
    pool = [key for key in dict.fromkeys(candidates) if key and key != "player"]
    wanted = rule.wanted_gender(player_gender)
    preferred = [key for key in pool if wanted is None or genders.get(key) == wanted]
    others = [key for key in pool if key not in preferred]
    chosen = rng.sample(preferred, min(rule.size, len(preferred)))
    if len(chosen) < rule.size:
        chosen += rng.sample(others, min(rule.size - len(chosen), len(others)))
    return chosen


def stage_opening_scene(state: "GameState", rng: Optional[random.Random] = None) -> list[str]:
    """Apply the story's welcome party to a freshly created game state.

    Returns the chosen greeter keys (also stored on ``state.opening_cast``);
    an empty list when the story authors no welcome party.
    """
    story_cfg = getattr(state, "story_cfg", None) or {}
    opening_cfg = story_cfg.get("opening") or {}
    rule = WelcomePartyRule.from_config(opening_cfg.get("welcome_party"))
    if rule is None:
        return []
    characters = getattr(state, "characters", None) or {}
    lifecycle = getattr(state, "cast_lifecycle", None)
    candidates = list(lifecycle.active_ids()) if lifecycle else [k for k in characters if k != "player"]
    party = choose_welcome_party(
        candidates,
        {key: character_gender(characters.get(key)) for key in candidates},
        getattr(state, "gender", None),
        rule,
        rng,
    )
    start = str(getattr(state, "location_id", "") or "")
    if start:
        locations = dict(getattr(state, "character_locations", None) or {})
        fallback = rule.fallback_location_id or str(
            (story_cfg.get("cast_lifecycle") or {}).get("initial_active_location_id") or ""
        )
        # Without a distinct room to send them to, others stay put: an
        # untracked resident would make whereabouts unanswerable.
        if rule.exclusive and fallback and fallback != start:
            for key, location in list(locations.items()):
                if key != "player" and key not in party and location == start:
                    locations[key] = fallback
        for key in party:
            locations[key] = start
        state.character_locations = locations
    if party:
        # The focal lens must be someone actually in the room.
        state.main_character_id = party[0]
    state.opening_cast = list(party)
    arrival_cfg = opening_cfg.get("arrival_sequence") or {}
    if arrival_cfg and party:
        offsets = [int(value) for value in arrival_cfg.get("offset_minutes") or []]
        waiting = [key for key in candidates if key not in party]
        if len(offsets) != len(waiting) or offsets != sorted(set(offsets)) or any(value <= 0 for value in offsets):
            raise ValueError("opening.arrival_sequence needs one distinct positive offset per waiting resident")
        chooser = rng or secrets.SystemRandom()
        chooser.shuffle(waiting)
        state.opening_arrival_minutes = dict(zip(waiting, offsets))
        state.opening_arrived_ids = []
        state.character_locations = {
            key: value for key, value in state.character_locations.items() if key not in waiting
        }
    return party


def has_arrived(state: "GameState", character_id: str) -> bool:
    """A reserved opening resident is not publicly present until their entrance fires."""
    scheduled = getattr(state, "opening_arrival_minutes", None) or {}
    return character_id not in scheduled or character_id in (getattr(state, "opening_arrived_ids", None) or [])


def advance_opening_arrivals(state: "GameState", minute_before: int, minute_after: int) -> list[str]:
    """Place due residents exactly once, in the story's authored gathering room."""
    scheduled = getattr(state, "opening_arrival_minutes", None) or {}
    arrived = set(getattr(state, "opening_arrived_ids", None) or [])
    due = [key for key, minute in sorted(scheduled.items(), key=lambda item: item[1])
           if key not in arrived and minute_before < minute <= minute_after]
    if not due:
        return []
    cfg = ((getattr(state, "story_cfg", None) or {}).get("opening") or {}).get("arrival_sequence") or {}
    room = str(cfg.get("gather_location_id") or getattr(state, "location_id", "") or "")
    if not room:
        raise ValueError("opening arrivals need a gathering location")
    model = getattr(state, "world_model", None)
    for key in due:
        state.character_locations[key] = room
        if model is not None and key in model.characters:
            model.world.move(key, room)
        arrived.add(key)
    state.opening_arrived_ids = list(getattr(state, "opening_arrived_ids", None) or []) + due
    return due


def opening_arrival_segments(state: "GameState") -> list[dict[str, str | None]]:
    """Guaranteed, authored entrance beats for residents the player can see."""
    due = getattr(state, "opening_arrivals_this_turn", None) or []
    cfg = ((getattr(state, "story_cfg", None) or {}).get("opening") or {}).get("arrival_sequence") or {}
    if not due or str(getattr(state, "location_id", "") or "") != str(cfg.get("gather_location_id") or ""):
        return []
    cues = cfg.get("entrance_cues") or {}
    lines = cfg.get("entrance_lines") or {}
    characters = getattr(state, "characters", {}) or {}
    beats: list[dict[str, str | None]] = []
    for key in due:
        name = str(getattr(characters.get(key), "name", None) or key)
        # The narrator never names a newcomer: the player learns who they are from their own introduction.
        beats.append({"kind": "narration", "speaker_id": None,
                      "text": "The front door opens. "
                              + str(cues.get(key) or "Someone steps into the living room with a bag.")})
        beats.append({"kind": "dialogue", "speaker_id": key,
                      "text": str(lines.get(key) or f"Hajimemashite. {name}.")})
    return beats


def group_ritual_brief(state: "GameState") -> str:
    """The show's first group question, once, on the turn after the last resident has arrived.

    Configured as ``opening.group_ritual`` (``prompt``, ``likes``/``dislikes`` taste-tag -> phrase). Each present
    resident gets hints drawn from their own authored tastes, so the answer teaches the player something true
    without listing it. Generic: any story can author its own ritual.
    """
    cfg = ((getattr(state, "story_cfg", None) or {}).get("opening") or {}).get("group_ritual") or {}
    scheduled = getattr(state, "opening_arrival_minutes", None) or {}
    if not cfg or getattr(state, "opening_ritual_done", True) or not scheduled:
        return ""
    if not set(scheduled) <= set(getattr(state, "opening_arrived_ids", None) or []):
        return ""
    if getattr(state, "opening_arrivals_this_turn", None):
        return ""
    from backend.app.engine.rules.personality import personalities

    room = str(getattr(state, "location_id", "") or "")
    locations = getattr(state, "character_locations", None) or {}
    characters = getattr(state, "characters", None) or {}
    people = personalities(getattr(state, "story_cfg", None) or {})
    likes, dislikes = cfg.get("likes") or {}, cfg.get("dislikes") or {}
    rows = []
    for key, where in sorted(locations.items()):
        if key == "player" or where != room or key not in people:
            continue
        tastes = people[key].tastes
        hints = [likes[tag] for tag, w in sorted(tastes.items(), key=lambda kv: -kv[1])[:2] if w > 0 and tag in likes]
        hints += [dislikes[tag] for tag, w in sorted(tastes.items(), key=lambda kv: kv[1])[:1] if w <= -2.0 and tag in dislikes]
        name = (getattr(characters.get(key), "name", None) or key).strip()
        rows.append(f"{name}: " + ("; ".join(hints) if hints else "no strong type"))
    if not rows:
        return ""
    return (
        f"Group moment, once: {cfg.get('prompt', 'The producers ask everyone what their type is.')} Only two or three "
        "residents answer in this reply, in their own voice and still as near-strangers; the rest pass, deflect or say "
        "they will go later. An answer is vague, shy, joking or sideways, never a list and never about anyone in the "
        "room. Put the leaning in your own words and never repeat the hint wording; one resident may dodge entirely. "
        "Each answerer lets slip at most ONE hint from their real leaning: " + " | ".join(rows) + ". Show it, do not "
        "announce it. The player is not asked yet; leave the reply open for the player.\n\n"
    )


def mark_group_ritual(state: "GameState") -> None:
    """Record that the ritual has been handed to the storyteller (call only when its brief was used)."""
    state.opening_ritual_done = True


# A narration repeats an authored entrance when it recovers this share of the cue's DISTINCTIVE words (the words no
# other resident's cue uses: "woman", "room" and "bows" describe every entrance), and at least MIN_SHARED_CUE_WORDS
# of them, so a short cue is never matched by coincidence.
CUE_REPEAT_SHARE = 0.4
MIN_SHARED_CUE_WORDS = 2


def _content_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']{4,}", text.lower()))


def repeats_entrance_cue(body: str, cue: str, other_cues: Iterable[str] = ()) -> bool:
    """Is `body` a retelling of the authored entrance `cue`? Authored cues never name the newcomer, so a retelling
    does not either: compare what is described, not who."""
    shared_with_others = set().union(*(_content_words(other) for other in other_cues if other != cue))
    wanted = _content_words(cue) - shared_with_others
    shared = len(wanted & _content_words(body))
    return shared >= MIN_SHARED_CUE_WORDS and shared >= CUE_REPEAT_SHARE * len(wanted)


def strip_generated_arrival_repeats(state: "GameState", segments: list[dict]) -> list[dict]:
    """Keep one visible entrance and self-introduction when the storyteller also drafts them.

    The server shows the authored beats first; a generated narration is dropped when it names an arriving resident
    while describing an entrance, or retells that resident's authored cue (the narrator never names newcomers, so
    the cue match is what catches an unnamed retelling, BL-93)."""
    due = set(getattr(state, "opening_arrivals_this_turn", None) or [])
    if not due:
        return segments
    characters = getattr(state, "characters", {}) or {}
    names = [str(getattr(characters.get(key), "name", None) or key) for key in due]
    arrival = ((getattr(state, "story_cfg", None) or {}).get("opening") or {}).get("arrival_sequence") or {}
    all_cues = {key: str(cue) for key, cue in (arrival.get("entrance_cues") or {}).items()}
    cues = [cue for key, cue in all_cues.items() if key in due]
    arrival_verb = re.compile(r"\b(?:arriv\w*|enter\w*|step\w*|walk\w*|door|come(?:s|ing)? in)\b", re.I)
    kept = []
    for segment in segments:
        if segment.get("kind") == "dialogue" and segment.get("speaker_id") in due:
            continue
        body = str(segment.get("text") or "")
        if segment.get("kind") == "narration":
            names_an_entrance = arrival_verb.search(body) and any(
                re.search(r"\b" + re.escape(name.split()[0]) + r"\b", body, re.I) for name in names)
            if names_an_entrance or any(repeats_entrance_cue(body, cue, all_cues.values()) for cue in cues):
                continue
        kept.append(segment)
    return kept


def opening_scene_brief(state: "GameState") -> str:
    """First-reply guidance so the storyteller continues the staged welcome."""
    party = [key for key in (getattr(state, "opening_cast", None) or []) if key]
    if not party or int(getattr(state, "turns", 0) or 0) != 0:
        return ""
    characters = getattr(state, "characters", None) or {}
    names = [(getattr(characters.get(key), "name", None) or key).strip() for key in party]
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    if getattr(state, "opening_arrival_minutes", None):
        return (
            f"Opening scene: {who} met the player, who entered second at 3 pm. "
            "Only this resident is with the player at the start. Let them have a real, slightly awkward "
            "first conversation. The other selected residents have not arrived yet and must not speak or "
            "be named before their entrance events. Nobody is eating; food can be ordered or prepared "
            "after the group has formed.\n\n"
        )
    return (
        f"Opening scene: {who} just greeted the player as the story opened, and they are "
        "the characters with the player right now. Continue this first conversation with "
        "them; everyone else is elsewhere and should only appear if someone actually goes "
        "to them or they plausibly walk in.\n\n"
    )

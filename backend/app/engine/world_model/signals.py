"""Affinity signals: liking shows as small, ambiguous behaviour, never as a stated feeling (generic, any story).

People rarely announce that they like someone; they ask one more question, hold a pause, stand a little nearer. This
module decides, deterministically per (seed, turn, person), whether one present person shows such a behaviour this
turn and how strong it is. It reads only the person's standing toward the player (relative to everyone present) and
their temperament, so it works for romance, friendship or any other standing track.

The player must never get a reliable read, so:
- the person who likes the player most signals most often, but others sometimes do the same (polite decoys);
- early or low liking only ever produces the subtlest behaviour;
- the wording is always framed to the storyteller as "could be politeness or interest".

Stories may replace the wording with `signals.catalogue` ({"1": [...], "2": [...], "3": [...]}); the levels are fixed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Mapping, Optional

LEADER_RATE = 0.45
DECOY_RATE = 0.10
COOLDOWN_TURNS = 3
SUBTLE_BELOW = 0.35        # interest below this: level 1 only
STRONG_FROM = 0.70         # interest from this: level 3 allowed
DECOY_BELOW = 0.15         # a person this indifferent can only be politely subtle

DEFAULT_CATALOGUE: dict[int, tuple[str, ...]] = {
    1: ("asks the player one more question than they ask anyone else",
        "answers the player a beat slower than the others, as if weighing it",
        "picks up a small detail the player mentioned earlier and brings it back in passing"),
    2: ("teases the player lightly, in a way that could be fondness or mockery",
        "ends up standing or sitting a little nearer the player without remarking on it",
        "mentions the player to someone else as if offhand"),
    3: ("looks for a reason to get a moment alone with the player",
        "rearranges a plan so the player is part of it"),
}


@dataclass(frozen=True)
class Candidate:
    """A present person who could signal: interest 0..1 (see `interest_of`), openness and pride 0..1."""
    cid: str
    interest: float
    openness: float
    pride: float


def interest_of(value: float, spec: Any) -> float:
    """Standing as 0..1 of the way to the track's last tier (its penultimate ceiling), so 'getting there' reads high."""
    tiers = list(getattr(spec, "tiers", None) or [])
    if not tiers:
        return 0.0
    top = tiers[-2].ceiling if len(tiers) > 1 else tiers[-1].ceiling
    return max(0.0, min(1.0, float(value) / float(top))) if top else 0.0


def signal_catalogue(story_cfg: Mapping[str, Any]) -> dict[int, tuple[str, ...]]:
    """The story's wording per level, or the engine default; every level must have at least one behaviour."""
    raw = ((story_cfg or {}).get("signals") or {}).get("catalogue")
    if not raw:
        return dict(DEFAULT_CATALOGUE)
    catalogue = {int(level): tuple(str(t).strip() for t in texts if str(t).strip()) for level, texts in raw.items()}
    if set(catalogue) != {1, 2, 3} or not all(catalogue.values()):
        raise ValueError("signals.catalogue needs levels 1, 2 and 3, each with at least one behaviour")
    return catalogue


def _intensity(candidate: Candidate, leader: bool) -> int:
    if not leader or candidate.interest < DECOY_BELOW:
        return 1
    level = 1 + (candidate.interest >= SUBTLE_BELOW) + (candidate.interest >= STRONG_FROM)
    if candidate.openness >= 0.7:
        level += 1
    elif candidate.openness <= 0.3:
        level -= 1
    return max(1, min(3, level))


def choose_signal(candidates: list[Candidate], turn: int, seed: str, last_turn: Mapping[str, int],
                  catalogue: Mapping[int, tuple[str, ...]]) -> Optional[tuple[str, str]]:
    """(person, behaviour) for the one signal this turn, or None. Deterministic for a given seed and turn."""
    if not candidates:
        return None
    best = max(c.interest for c in candidates)
    leader_id = min((c.cid for c in candidates if c.interest == best), default="") if best > 0 else ""
    for cand in sorted(candidates, key=lambda c: (c.cid != leader_id, c.cid)):
        if turn - last_turn.get(cand.cid, -99) < COOLDOWN_TURNS:
            continue
        is_leader = cand.cid == leader_id
        rate = (LEADER_RATE if is_leader else DECOY_RATE) * max(0.1, 1.2 - 0.6 * cand.pride)
        rng = random.Random(f"{seed}:signal:{turn}:{cand.cid}")
        if rng.random() < rate:
            return cand.cid, rng.choice(catalogue[_intensity(cand, is_leader)])
    return None

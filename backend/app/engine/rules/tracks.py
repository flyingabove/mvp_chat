"""Story-declared standing tracks: tiers, gates and personal requirements.

Declared in story JSON under `social_tracks`; numbers are tuning, not engine
truth. A tier's gate must hold to ENTER that tier. Requirements attach to a
tier: `cap` requirements also gate entering it; `dealbreaker` requirements
close the whole track once their condition is established false.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.engine.rules.conditions import Condition, parse

DISCLOSURES = frozenset({"hidden", "hint", "open"})


@dataclass(frozen=True)
class Tier:
    id: str
    floor: float
    ceiling: float
    gate: Optional[Condition] = None


@dataclass(frozen=True)
class TrackSpec:
    id: str
    tiers: tuple[Tier, ...]
    daily_gain_cap: float
    repeat_decay: float
    neglect_decay_per_day: float = 0.0
    version: int = 1

    def tier_of(self, value: float) -> Tier:
        for tier in self.tiers:
            if value <= tier.ceiling:
                return tier
        return self.tiers[-1]

    def tier_index(self, tier_id: str) -> int:
        return next(i for i, t in enumerate(self.tiers) if t.id == tier_id)


@dataclass(frozen=True)
class Requirement:
    id: str
    track: str
    tier: str
    condition: Condition
    on_fail: str = "cap"            # cap | dealbreaker
    disclosure: str = "hidden"      # hidden | hint | open
    tell: str = ""


@dataclass(frozen=True)
class SocialRules:
    tracks: dict[str, TrackSpec]
    requirements: dict[str, tuple[Requirement, ...]]   # character id or "default" -> requirements

    def requirements_for(self, owner: str, track: str) -> tuple[Requirement, ...]:
        own = self.requirements.get(owner)
        chosen = own if own is not None else self.requirements.get("default", ())
        return tuple(r for r in chosen if r.track == track)


def _tier(raw: dict[str, Any]) -> Tier:
    gate = raw.get("gate")
    return Tier(_text(raw, "id"), float(raw["floor"]), float(raw["ceiling"]), parse(gate) if gate else None)


def _track(raw: dict[str, Any]) -> TrackSpec:
    tiers = tuple(_tier(t) for t in raw.get("tiers") or [])
    if not tiers:
        raise ValueError(f"track {raw.get('id')!r} needs tiers")
    previous_ceiling = None
    for tier in tiers:
        if tier.ceiling <= tier.floor:
            raise ValueError(f"tier {tier.id!r} ceiling must exceed its floor")
        if previous_ceiling is not None and tier.floor != previous_ceiling:
            raise ValueError(f"tier {tier.id!r} must start where the previous tier ends")
        previous_ceiling = tier.ceiling
    if tiers[0].gate is not None:
        raise ValueError("the first tier cannot have a gate")
    if len({t.id for t in tiers}) != len(tiers):
        raise ValueError("tier ids must be unique")
    spec = TrackSpec(_text(raw, "id"), tiers, float(raw.get("daily_gain_cap", 10)), float(raw.get("repeat_decay", 0.5)),
                     float(raw.get("neglect_decay_per_day", 0)), int(raw.get("version", 1)))
    if spec.daily_gain_cap <= 0 or not 0 <= spec.repeat_decay <= 1 or spec.neglect_decay_per_day < 0:
        raise ValueError(f"track {spec.id!r} has invalid tuning")
    return spec


def _requirement(raw: dict[str, Any], tracks: dict[str, TrackSpec]) -> Requirement:
    req = Requirement(_text(raw, "id"), _text(raw, "track"), _text(raw, "tier"), parse(raw.get("condition")),
                      str(raw.get("on_fail") or "cap"), str(raw.get("disclosure") or "hidden"), str(raw.get("tell") or ""))
    if req.track not in tracks:
        raise ValueError(f"requirement {req.id!r} names unknown track {req.track!r}")
    if req.tier not in {t.id for t in tracks[req.track].tiers}:
        raise ValueError(f"requirement {req.id!r} names unknown tier {req.tier!r}")
    if req.on_fail not in ("cap", "dealbreaker") or req.disclosure not in DISCLOSURES:
        raise ValueError(f"requirement {req.id!r} has invalid on_fail/disclosure")
    return req


def social_rules(story_cfg: dict[str, Any]) -> Optional[SocialRules]:
    """Parse `social_tracks`; None when a story declares no tracks."""
    raw = (story_cfg or {}).get("social_tracks")
    if not raw:
        return None
    tracks: dict[str, TrackSpec] = {}
    for item in raw.get("tracks") or []:
        spec = _track(item)
        if spec.id in tracks:
            raise ValueError(f"duplicate track {spec.id!r}")
        tracks[spec.id] = spec
    requirements = {str(owner): tuple(_requirement(r, tracks) for r in items)
                    for owner, items in (raw.get("requirements") or {}).items()}
    for items in requirements.values():
        ids = [r.id for r in items]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique per character")
    return SocialRules(tracks, requirements)


def _text(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key!r} is required: {raw}")
    return value

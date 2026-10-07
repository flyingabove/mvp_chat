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
class AppraisalPolicy:
    """How observed behavior turns into impressions (tuning, story-declared)."""
    track: str
    gain_scale: float = 3.0          # standing points per unit of taste when done TO the holder
    witness_scale: float = 0.3       # fraction applied when the holder only watched it done to someone else
    feeling_scale: float = 0.02      # affection change per unit of taste
    romantic_tags: frozenset[str] = frozenset()
    jealousy_tier: str = ""          # holder's tier toward the actor from which romantic acts elsewhere sting
    eligible: str = "any"            # any | opposite_gender: which holder->actor pairs this track covers
    offscreen_scale: float = 1.0     # pace of off-screen relationship change between residents

    def covers(self, holder_gender: str, actor_gender: str) -> bool:
        if self.eligible == "any":
            return True
        return bool(holder_gender) and bool(actor_gender) and holder_gender != actor_gender


@dataclass(frozen=True)
class CouplePolicy:
    """When NPCs pursue, pair up and leave together (tiers on the appraisal track)."""
    interested_tier: str
    dating_tier: str
    committed_tier: str
    days_together: int = 2
    rival_aim: float = 0.0     # BL-34: priority (0-1) of the own romantic aim each rival starts with; 0 = off


INTENSITY_PRESETS = {"off": 0.0, "low": 0.35, "medium": 0.65, "high": 1.0}


@dataclass(frozen=True)
class Intensity:
    """How hard a story leans on social drama (0 = off, 1 = full). Dating games run it on `high`.

    `romance` scales the romantic mechanics (jealousy, the cost of a refused confession); `rivalry` scales competition
    for a partner (rival aims, a rival seeing an opening, off-screen contests, rival invitations). `high` (1.0) is the
    pre-knob behaviour, so a story that does not say reads as `high`; a story with no couples or appraisal policy
    has none of these mechanics to scale."""
    romance: float = 1.0
    rivalry: float = 1.0


@dataclass(frozen=True)
class DramaTuning:
    """Strengths of the social consequences a story can tune (`social_tracks.tuning`); the defaults are the engine's own.

    `witness_loss`/`refuser_loss`: standing points off the asker after a refused confession; `rival_aim`: priority of the aim
    a rival takes on after seeing it; `contest_plan`/`contest_affection`: how much a live contest over a partner raises an
    off-screen plan or an affectionate meeting (before the `rivalry` intensity scales them)."""
    witness_loss: float = 2.0
    refuser_loss: float = 2.5
    rival_aim: float = 0.5
    contest_plan: float = 1.0
    contest_affection: float = 0.5


@dataclass(frozen=True)
class SocialRules:
    tracks: dict[str, TrackSpec]
    requirements: dict[str, tuple[Requirement, ...]]   # character id or "default" -> requirements
    appraisal: Optional[AppraisalPolicy] = None
    couples: Optional[CouplePolicy] = None
    intensity: Intensity = Intensity()
    tuning: DramaTuning = DramaTuning()

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
    appraisal = _appraisal(raw.get("appraisal"), tracks)
    return SocialRules(tracks, requirements, appraisal, _couples(raw.get("couples"), tracks, appraisal),
                       _intensity(raw.get("intensity")), _tuning(raw.get("tuning")))


def _tuning(raw: Any) -> DramaTuning:
    if raw is None:
        return DramaTuning()
    fields = set(DramaTuning.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) - fields:
        raise ValueError(f"tuning must be an object with only {sorted(fields)}")
    values = {}
    for key, value in raw.items():
        try:
            values[key] = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"tuning {key} must be a number") from None
        if values[key] < 0:
            raise ValueError(f"tuning {key} must not be negative")
    return DramaTuning(**values)


def _intensity(raw: Any) -> Intensity:
    """`"intensity": "high"` sets both knobs; `{"romance": "low", "rivalry": 0.8}` sets each (a preset name or 0 to 1)."""
    if raw is None:
        return Intensity()
    parts = {"romance": raw, "rivalry": raw} if not isinstance(raw, dict) else {
        key: raw.get(key, "high") for key in ("romance", "rivalry")}
    unknown = set(raw) - {"romance", "rivalry"} if isinstance(raw, dict) else set()
    if unknown:
        raise ValueError(f"unknown intensity knob(s) {sorted(unknown)}")
    values = {}
    for key, value in parts.items():
        if isinstance(value, str):
            if value not in INTENSITY_PRESETS:
                raise ValueError(f"intensity {key} must be one of {sorted(INTENSITY_PRESETS)} or a number from 0 to 1")
            values[key] = INTENSITY_PRESETS[value]
        else:
            values[key] = _fraction(value, f"intensity {key}")
    return Intensity(values["romance"], values["rivalry"])


def _fraction(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number between 0 and 1") from None
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


def _couples(raw: Optional[dict[str, Any]], tracks: dict[str, TrackSpec],
             appraisal: Optional[AppraisalPolicy]) -> Optional[CouplePolicy]:
    if not raw:
        return None
    if appraisal is None:
        raise ValueError("couples need an appraisal track")
    policy = CouplePolicy(_text(raw, "interested_tier"), _text(raw, "dating_tier"), _text(raw, "committed_tier"),
                          int(raw.get("days_together", 2)), _fraction(raw.get("rival_aim", 0), "rival_aim"))
    tiers = {t.id for t in tracks[appraisal.track].tiers}
    for tier in (policy.interested_tier, policy.dating_tier, policy.committed_tier):
        if tier not in tiers:
            raise ValueError(f"couples name unknown tier {tier!r}")
    if policy.days_together < 0:
        raise ValueError("days_together must be >= 0")
    return policy


def _appraisal(raw: Optional[dict[str, Any]], tracks: dict[str, TrackSpec]) -> Optional[AppraisalPolicy]:
    if not raw:
        return None
    policy = AppraisalPolicy(_text(raw, "track"), float(raw.get("gain_scale", 3.0)),
                             float(raw.get("witness_scale", 0.3)), float(raw.get("feeling_scale", 0.02)),
                             frozenset(raw.get("romantic_tags") or []), str(raw.get("jealousy_tier") or ""),
                             str(raw.get("eligible") or "any"), float(raw.get("offscreen_scale", 1.0)))
    if policy.offscreen_scale < 0:
        raise ValueError("offscreen_scale must be >= 0")
    if policy.eligible not in ("any", "opposite_gender"):
        raise ValueError(f"unknown appraisal eligibility {policy.eligible!r}")
    if policy.track not in tracks:
        raise ValueError(f"appraisal names unknown track {policy.track!r}")
    if policy.jealousy_tier and policy.jealousy_tier not in {t.id for t in tracks[policy.track].tiers}:
        raise ValueError(f"appraisal names unknown jealousy tier {policy.jealousy_tier!r}")
    if policy.gain_scale <= 0 or not 0 <= policy.witness_scale <= 1 or policy.feeling_scale < 0:
        raise ValueError("appraisal scales out of range")
    return policy


def _text(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key!r} is required: {raw}")
    return value

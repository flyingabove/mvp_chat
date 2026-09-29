"""Per-bond standing on story tracks, written only through StandingBook.

Every change is an AppliedEffect with its cause, in one ordered journal.
Replay re-applies the recorded applied amounts (never re-evaluates proposals
under new tuning). Old journal entries fold into a checkpoint so memory stays
bounded while replay still reproduces the same standings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.app.engine.rules.tracks import Tier, TrackSpec

JOURNAL_LIMIT = 400
Key = tuple[str, str, str]   # owner, target, track


@dataclass
class Standing:
    value: float = 0.0
    closed_by: str = ""
    day_gain: dict[int, float] = field(default_factory=dict)
    tag_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "closed_by": self.closed_by,
                "day_gain": {str(k): v for k, v in self.day_gain.items()}, "tag_counts": dict(self.tag_counts)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Standing":
        return cls(float(raw.get("value") or 0), str(raw.get("closed_by") or ""),
                   {int(k): float(v) for k, v in (raw.get("day_gain") or {}).items()},
                   {str(k): int(v) for k, v in (raw.get("tag_counts") or {}).items()})


@dataclass(frozen=True)
class Impression:
    """A proposed change: why one person's standing toward another should move."""
    effect_id: str
    owner: str
    target: str
    track: str
    tag: str
    delta: float
    cause_event_id: str
    minute: int
    day: int
    channel: str = "witnessed"


@dataclass(frozen=True)
class AppliedEffect:
    effect_id: str
    kind: str            # gain | loss | decay | close
    owner: str
    target: str
    track: str
    tag: str
    proposed: float
    applied: float
    cause_event_id: str
    minute: int
    day: int
    sequence: int
    policy_version: int
    closed_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppliedEffect":
        return cls(**raw)


class StandingBook:
    def __init__(self) -> None:
        self.standings: dict[Key, Standing] = {}
        self.journal: list[AppliedEffect] = []
        self.sequence = 0
        self.checkpoint: dict[str, Any] = {"sequence": 0, "standings": {}, "effect_ids": []}
        self._applied_ids: set[str] = set()
        self.specs: dict[str, TrackSpec] = {}

    # -- reads -----------------------------------------------------------------------------
    def bind(self, specs: dict[str, TrackSpec]) -> "StandingBook":
        self.specs = dict(specs)
        return self

    def get(self, owner: str, target: str, track: str) -> Optional[Standing]:
        return self.standings.get((owner, target, track))

    def tier(self, owner: str, target: str, track: str) -> Optional[Tier]:
        spec = self.specs.get(track)
        if spec is None:
            return None
        standing = self.get(owner, target, track)
        return spec.tier_of(standing.value if standing else 0.0)

    def tier_reached(self, owner: str, target: str, track: str, tier_id: str) -> Optional[bool]:
        spec = self.specs.get(track)
        if spec is None or tier_id not in {t.id for t in spec.tiers}:
            return None
        current = self.tier(owner, target, track)
        return spec.tier_index(current.id) >= spec.tier_index(tier_id)

    # -- the only writers ------------------------------------------------------------------
    def apply(self, impression: Impression, gate_open: Callable[[Tier], bool] = lambda tier: False) -> AppliedEffect:
        """Apply one impression under its track's rules. Idempotent by effect id."""
        existing = self._existing(impression.effect_id)
        if existing is not None:
            return existing
        spec = self.specs[impression.track]
        standing = self.standings.setdefault((impression.owner, impression.target, impression.track), Standing())
        if impression.delta < 0:
            kind, applied = "loss", max(impression.delta, -standing.value)
        elif standing.closed_by:
            kind, applied = "gain", 0.0
        else:
            kind = "gain"
            tag_key = f"{impression.day}:{impression.tag}"
            decayed = impression.delta * spec.repeat_decay ** standing.tag_counts.get(tag_key, 0)
            allowance = max(0.0, spec.daily_gain_cap - standing.day_gain.get(impression.day, 0.0))
            ceiling = self._reachable_ceiling(spec, standing.value, gate_open)
            applied = max(0.0, min(decayed, allowance, ceiling - standing.value))
        return self._record(impression.effect_id, kind, impression, impression.delta, applied, spec.version)

    def decay(self, owner: str, target: str, track: str, day: int, days: int, minute: int) -> Optional[AppliedEffect]:
        """Neglect over `days` whole days: an explicit, ordered clock effect."""
        spec = self.specs[track]
        standing = self.get(owner, target, track)
        if standing is None or days <= 0 or spec.neglect_decay_per_day <= 0:
            return None
        amount = -min(standing.value, spec.neglect_decay_per_day * days)
        proposal = Impression(f"decay:{owner}:{target}:{track}:{day}", owner, target, track, "neglect",
                              amount, "", minute, day, "clock")
        return self._existing(proposal.effect_id) or self._record(proposal.effect_id, "decay", proposal, amount,
                                                                  amount, spec.version)

    def close(self, owner: str, target: str, track: str, requirement_id: str, cause_event_id: str,
              minute: int, day: int) -> Optional[AppliedEffect]:
        standing = self.standings.setdefault((owner, target, track), Standing())
        if standing.closed_by:
            return None
        proposal = Impression(f"close:{owner}:{target}:{track}:{requirement_id}", owner, target, track,
                              requirement_id, 0.0, cause_event_id, minute, day, "rule")
        return self._existing(proposal.effect_id) or self._record(
            proposal.effect_id, "close", proposal, 0.0, 0.0, self.specs[track].version, closed_by=requirement_id)

    # -- internals ---------------------------------------------------------------------------
    @staticmethod
    def _reachable_ceiling(spec: TrackSpec, value: float, gate_open: Callable[[Tier], bool]) -> float:
        index = spec.tier_index(spec.tier_of(value).id)
        ceiling = spec.tiers[index].ceiling
        for tier in spec.tiers[index + 1:]:
            if gate_open(tier) is not True:
                break
            ceiling = tier.ceiling
        return ceiling

    def _existing(self, effect_id: str) -> Optional[AppliedEffect]:
        if effect_id not in self._applied_ids and effect_id not in self.checkpoint["effect_ids"]:
            return None
        return next((e for e in self.journal if e.effect_id == effect_id), None) or AppliedEffect(
            effect_id, "duplicate", "", "", "", "", 0.0, 0.0, "", 0, 0, -1, 0)

    def _record(self, effect_id: str, kind: str, source: Impression, proposed: float, applied: float,
                version: int, closed_by: str = "") -> AppliedEffect:
        self.sequence += 1
        effect = AppliedEffect(effect_id, kind, source.owner, source.target, source.track, source.tag, proposed,
                               applied, source.cause_event_id, source.minute, source.day, self.sequence,
                               version, closed_by)
        self._apply_effect(effect)
        self.journal.append(effect)
        self._applied_ids.add(effect_id)
        self._fold_old_entries()
        return effect

    def _apply_effect(self, effect: AppliedEffect) -> None:
        standing = self.standings.setdefault((effect.owner, effect.target, effect.track), Standing())
        standing.value += effect.applied
        if effect.kind == "gain":
            standing.day_gain[effect.day] = standing.day_gain.get(effect.day, 0.0) + effect.applied
            key = f"{effect.day}:{effect.tag}"
            standing.tag_counts[key] = standing.tag_counts.get(key, 0) + 1
        if effect.kind == "close":
            standing.closed_by = effect.closed_by

    def _fold_old_entries(self) -> None:
        if len(self.journal) <= JOURNAL_LIMIT:
            return
        folded = self.journal[:-JOURNAL_LIMIT]
        base = StandingBook._from_snapshot(self.checkpoint)
        for effect in folded:
            base._apply_effect(effect)
        self.checkpoint = {"sequence": folded[-1].sequence,
                           "standings": {"|".join(k): s.to_dict() for k, s in base.standings.items()},
                           "effect_ids": list(self.checkpoint["effect_ids"]) + [e.effect_id for e in folded]}
        self.journal = self.journal[-JOURNAL_LIMIT:]

    @staticmethod
    def _from_snapshot(checkpoint: dict[str, Any]) -> "StandingBook":
        book = StandingBook()
        book.standings = {tuple(k.split("|")): Standing.from_dict(v)
                          for k, v in (checkpoint.get("standings") or {}).items()}
        return book

    def replay(self) -> dict[Key, Standing]:
        """Standings rebuilt from the checkpoint plus the applied journal, in order."""
        book = StandingBook._from_snapshot(self.checkpoint)
        for effect in sorted(self.journal, key=lambda e: e.sequence):
            book._apply_effect(effect)
        return book.standings

    # -- persistence -----------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"standings": {"|".join(k): s.to_dict() for k, s in self.standings.items()},
                "journal": [e.to_dict() for e in self.journal], "sequence": self.sequence,
                "checkpoint": self.checkpoint}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StandingBook":
        book = cls()
        book.standings = {tuple(k.split("|")): Standing.from_dict(v) for k, v in (raw.get("standings") or {}).items()}
        book.journal = [AppliedEffect.from_dict(e) for e in raw.get("journal") or []]
        book.sequence = int(raw.get("sequence") or 0)
        book.checkpoint = raw.get("checkpoint") or {"sequence": 0, "standings": {}, "effect_ids": []}
        book._applied_ids = {e.effect_id for e in book.journal}
        return book

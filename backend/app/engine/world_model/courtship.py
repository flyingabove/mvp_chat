"""Who can court whom, and who competes: one place, driven by the story's data (generic, P-08 slice 2).

The engine never tests a literal gender. A story's appraisal policy says which holder-to-actor pairs its romantic track
covers (`eligible`: `any` or `opposite_gender`); this module turns that, plus each person's `gender` attribute, into the two
questions the mechanics ask:

- `eligible(a, b)`: can `a` be drawn to `b` on the story's track;
- `competes(a, b, partner)`: do `a` and `b` both stand to court `partner` (so each is the other's rival for them).

A story with a different or no romance track changes the answer by data alone; a workplace story with no appraisal policy
has no courtship at all.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.engine.rules.tracks import AppraisalPolicy, DramaTuning, Intensity
from backend.app.engine.world_model.model import PLAYER


class Courtship:
    def __init__(self, policy: Optional[AppraisalPolicy], genders: Mapping[str, str], intensity: Intensity = Intensity(),
                 tuning: DramaTuning = DramaTuning()):
        self.policy = policy
        self.genders = {str(k): str(v or "").upper() for k, v in genders.items()}
        self.intensity = intensity
        self.tuning = tuning

    @classmethod
    def of(cls, rules: Any, genders: Mapping[str, str]) -> "Courtship":
        return cls(getattr(rules, "appraisal", None), genders, getattr(rules, "intensity", None) or Intensity(),
                   getattr(rules, "tuning", None) or DramaTuning())

    @classmethod
    def opposite(cls, genders: Mapping[str, str]) -> "Courtship":
        """The contest a story's `romance_goal` (`partner_gender: opposite_player`) describes, for callers holding no rules."""
        return cls(AppraisalPolicy("", 3.0, 0.3, 0.02, frozenset(), "", "opposite_gender"), genders)

    @classmethod
    def from_context(cls, context: Mapping[str, Any]) -> "Courtship":
        """The courtship a `turn.rivalry_context` describes (it carries its own, hand-built contexts only the genders)."""
        built = context.get("courtship")
        if built is not None:
            return built
        genders = dict(context.get("genders") or {})
        genders[PLAYER] = context.get("player_gender") or ""
        return cls.opposite(genders)

    def eligible(self, a: str, b: str) -> bool:
        return self.policy is not None and a != b and self.policy.covers(self.genders.get(a, ""), self.genders.get(b, ""))

    def competes(self, a: str, b: str, partner: str) -> bool:
        return len({a, b, partner}) == 3 and self.eligible(a, partner) and self.eligible(b, partner)

    def rivals_of_player(self, candidates, partner: str) -> list[str]:
        return [c for c in candidates if c != PLAYER and self.competes(c, PLAYER, partner)]

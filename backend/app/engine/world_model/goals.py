"""Goals on the character (P-07, BL-85): what a person is after, how much, and how that changes.

A `Goal` is authored data (story JSON `personalities[key].goals`, parsed and validated by `rules/personality.py`):
a kind from a closed, story-extensible list, an optional target, a starting weight in 0..1 and `shifts`, each a
condition from `rules/conditions.py` judged from the HOLDER's own viewpoint that raises or lowers the weight once.
Nothing here knows a game: "love" and "keep_secret" mean the same in a house, a mystery or a heist.

`GoalBook` (on the `WorldModel`) is the only writer of live weights. A weight is stored only after it first changes,
as an `EvolvingTrait` (`social_traits.py`) so every change keeps its provenance; until then the authored weight stands,
so a save with no shifted goals stores nothing and old saves load unchanged. A shift fires once: the trait's history
holds the shift id, which is also what makes a retried turn a no-op.

Behaviour this task adds: the heaviest goal reaches the storyteller on the person's scene card, and goals scale the
priority of romantic aims (`agenda_scale`). A character with no goals is exactly neutral.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from backend.app.engine.rules.conditions import Condition, Viewpoint, parse
from backend.app.engine.social_traits import EvolvingTrait

GOAL_KINDS = ("love", "career", "status", "belonging", "keep_secret", "revenge", "protect", "chaos")
MAX_SHIFT = 1.0
STRONG, FAINT = 0.7, 0.3          # card wording thresholds
SCALE_SPAN = 0.5                  # love vs the strongest other goal moves romantic priority by up to +-50%
TRAIT_KIND = "goal_weight"


@dataclass(frozen=True)
class Shift:
    """A condition (holder's view) that moves a goal's weight by `delta`, once."""
    id: str
    condition: Condition
    delta: float
    reason: str


@dataclass(frozen=True)
class Goal:
    id: str
    kind: str
    target: str            # a character key, or "" when the goal is not about one person
    weight: float          # the authored starting weight; live weights come from the GoalBook
    shifts: tuple[Shift, ...] = ()
    text: str = ""         # optional authored wording for the card ("win the show")


@dataclass(frozen=True)
class WeightChange:
    owner: str
    goal_id: str
    old: float
    new: float
    reason: str


def parse_goals(raw: Any, owner: str, characters: Optional[set[str]] = None,
                extra_kinds: tuple[str, ...] = ()) -> tuple[Goal, ...]:
    """Validate and build one character's goals. Bad content raises ValueError naming the character and goal."""
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"goals for {owner!r} must be a list")
    kinds = set(GOAL_KINDS) | {str(k) for k in extra_kinds}
    goals: list[Goal] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"goal for {owner!r} must be an object: {item!r}")
        gid = str(item.get("id") or "").strip()
        if not gid:
            raise ValueError(f"goal for {owner!r} needs an id: {item!r}")
        where = f"goal {gid!r} of {owner!r}"
        if any(g.id == gid for g in goals):
            raise ValueError(f"duplicate goal id {gid!r} for {owner!r}")
        kind = str(item.get("kind") or "")
        if kind not in kinds:
            raise ValueError(f"{where}: unknown goal kind {kind!r}; choose from {sorted(kinds)}")
        weight = _number(item.get("weight"), f"{where} needs a numeric weight")
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"{where}: weight must be within 0..1")
        target = str(item.get("target") or "").strip()
        if target and characters is not None and target not in characters | {"player"}:
            raise ValueError(f"{where}: target is an unknown character {target!r}")
        goals.append(Goal(gid, kind, target, weight, _shifts(item.get("shifts"), gid, where),
                          str(item.get("text") or "").strip()))
    return tuple(goals)


def _number(value: Any, message: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(message)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(message) from None


def _shifts(raw: Any, gid: str, where: str) -> tuple[Shift, ...]:
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{where}: shifts must be a list")
    shifts = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{where}: a shift must be an object")
        try:
            condition = parse(item.get("when"))
        except ValueError as exc:
            raise ValueError(f"{where}: shift {index} has an unknown condition ({exc})") from None
        delta = _number(item.get("delta"), f"{where}: shift {index} needs a numeric delta")
        if abs(delta) > MAX_SHIFT:
            raise ValueError(f"{where}: shift {index} delta must be within -{MAX_SHIFT:g}..{MAX_SHIFT:g}")
        shifts.append(Shift(f"{gid}#{index}", condition, delta, str(item.get("reason") or condition.explain())))
    return tuple(shifts)


@dataclass
class GoalBook:
    """Live goal weights that have moved from their authored value, with the history of why."""
    traits: dict[str, EvolvingTrait] = field(default_factory=dict)      # "owner|goal id" -> weight trait

    @staticmethod
    def _key(owner: str, goal_id: str) -> str:
        return f"{owner}|{goal_id}"

    def trait(self, owner: str, goal_id: str) -> Optional[EvolvingTrait]:
        return self.traits.get(self._key(owner, goal_id))

    def weight(self, owner: str, goal: Goal) -> float:
        trait = self.trait(owner, goal.id)
        try:
            return float(trait.current) if trait is not None and trait.current else goal.weight
        except ValueError:
            return goal.weight

    def apply_shifts(self, model: Any, people: Mapping[str, Any], graph: Any, minute: int) -> list[WeightChange]:
        """Fire every shift whose condition holds from its owner's own view and has not fired yet."""
        changes: list[WeightChange] = []
        for owner in sorted(people):
            for goal in getattr(people[owner], "goals", ()):
                for shift in goal.shifts:
                    trait = self.trait(owner, goal.id)
                    if trait is not None and any(e.id == shift.id for e in trait.history):
                        continue
                    vp = Viewpoint(model=model, holder=owner, subject=goal.target or None, graph=graph,
                                   standings=model.standing)
                    if shift.condition.evaluate(vp) is not True:
                        continue
                    old = self.weight(owner, goal)
                    new = round(max(0.0, min(1.0, old + shift.delta)), 3)
                    if trait is None:
                        trait = EvolvingTrait(kind=TRAIT_KIND, subject_id=owner, target_id=goal.id)
                        trait.set_initial(f"{old:g}", minute=0)
                        self.traits[self._key(owner, goal.id)] = trait
                    if trait.propose_change(f"{new:g}", minute=minute, reason=shift.reason, confidence=1.0,
                                            entry_id=shift.id, source="system"):
                        changes.append(WeightChange(owner, goal.id, old, new, shift.reason))
                    else:                                  # clamped to no change: remember it fired, never retry
                        trait.history.append(_fired_marker(trait, shift, minute))
        return changes

    def to_dict(self) -> dict[str, Any]:
        return {key: trait.to_dict() for key, trait in sorted(self.traits.items())}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "GoalBook":
        return cls({str(k): EvolvingTrait.from_dict(v) for k, v in (data or {}).items()})


def _fired_marker(trait: EvolvingTrait, shift: Shift, minute: int):
    from backend.app.engine.knowledge_chunks import KnowledgeChunk
    return KnowledgeChunk(id=shift.id, content=trait.current, source="system", confidence=1.0,
                          timestamp_minute=minute, provenance=f"{shift.reason} (no change: already at the limit)")


def live_goals(book: GoalBook, owner: str, personality: Any) -> list[Goal]:
    """The person's goals with their current weights, in authored order."""
    return [Goal(g.id, g.kind, g.target, book.weight(owner, g), g.shifts, g.text)
            for g in getattr(personality, "goals", ())]


def active_goal(book: GoalBook, owner: str, personality: Any) -> Optional[Goal]:
    """The heaviest live goal (ties: lowest id); None when the person has none or all are at zero."""
    ranked = sorted((g for g in live_goals(book, owner, personality) if g.weight > 0), key=lambda g: (-g.weight, g.id))
    return ranked[0] if ranked else None


def card_note(goal: Goal, weight: float, names: Mapping[str, str]) -> str:
    """The storyteller's private line for a scene card. The aim steers behaviour; it is never announced."""
    what = goal.text or goal.kind.replace("_", " ") + (f", toward {names.get(goal.target, goal.target)}" if goal.target else "")
    strength = " (strong)" if weight >= STRONG else " (faint)" if weight <= FAINT else ""
    return f"private aim: {what}{strength}; never announce it"


def agenda_scale(book: GoalBook, owner: str, personality: Any) -> float:
    """Multiplier on the priority of this person's romantic aims: love against their strongest other goal.

    No goals gives exactly 1.0, so a story that configures none behaves as before."""
    goals = live_goals(book, owner, personality)
    if not goals:
        return 1.0
    love = max((g.weight for g in goals if g.kind == "love"), default=0.0)
    other = max((g.weight for g in goals if g.kind != "love"), default=0.0)
    return 1.0 + SCALE_SPAN * (love - other)

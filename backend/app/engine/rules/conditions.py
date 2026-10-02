"""One small typed condition language for tier gates, requirements, endings and clocks.

Conditions are declared in story JSON with a closed set of kinds and are
evaluated from a Viewpoint. A character viewpoint reads only that
character's own knowledge; the truth viewpoint is engine-privileged and never
reaches prompts. Evaluation is tri-state: True, False or None (unknown).
`Not(unknown)` stays unknown, so a missing fact can never trip a dealbreaker.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable, Optional

Tri = Optional[bool]

OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq, "!=": operator.ne,
}
FEELINGS = frozenset({"trust", "affection", "suspicion", "fear", "jealousy"})
ROLES = ("holder", "subject", "third")


@dataclass(frozen=True)
class Viewpoint:
    """Whose eyes a condition is judged through. holder=None means engine truth."""
    model: Any
    holder: Optional[str]
    subject: Optional[str] = None
    graph: Any = None
    standings: Any = None
    third: Optional[str] = None       # a third party: the rival's prize, a mutual friend (stance rules, P-08)
    people: Any = None                # character -> Personality (trait, strategy and goal_weight conditions)
    eligible: Any = None              # callable (a, b) -> bool: may these two be drawn to each other (story policy)
    levels: Any = None                # the story's acquaintance levels

    @property
    def is_truth(self) -> bool:
        return self.holder is None

    def who(self, role: str) -> Optional[str]:
        """The character a role names: holder | subject | third."""
        return {"holder": self.holder, "subject": self.subject, "third": self.third}[role]


class Condition:
    kind = ""

    def evaluate(self, vp: Viewpoint) -> Tri:
        raise NotImplementedError

    def explain(self) -> str:
        raise NotImplementedError

    def causes(self, vp: Viewpoint) -> tuple[str, ...]:
        """Ids of the world events this condition rests on (for provenance); most conditions rest on none."""
        return ()


def _num(raw: dict, key: str, default: Any = None) -> float:
    value = raw.get(key, default)
    if value is None or isinstance(value, bool):
        raise ValueError(f"condition needs numeric {key!r}: {raw}")
    return float(value)


def _op(raw: dict) -> str:
    op = str(raw.get("op") or ">=")
    if op not in OPS:
        raise ValueError(f"unknown comparison {op!r}")
    return op


@dataclass(frozen=True)
class Feeling(Condition):
    dimension: str
    op: str
    value: float
    toward: str = "subject"
    kind = "feeling"

    def evaluate(self, vp: Viewpoint) -> Tri:
        target = vp.who(self.toward)
        if vp.is_truth or not target or vp.graph is None:
            return None
        edge = vp.graph.get_edge(vp.holder, target)
        return None if edge is None else OPS[self.op](getattr(edge.state, self.dimension), self.value)

    def explain(self) -> str:
        return f"{self.dimension} {self.op} {self.value}"


@dataclass(frozen=True)
class StandingAtLeast(Condition):
    track: str
    value: float
    toward: str = "subject"
    kind = "standing_at_least"

    def evaluate(self, vp: Viewpoint) -> Tri:
        target = vp.who(self.toward)
        if vp.standings is None or not target or vp.holder is None:
            return None
        standing = vp.standings.get(vp.holder, target, self.track)
        return standing is not None and standing.value >= self.value

    def explain(self) -> str:
        return f"{self.track} standing >= {self.value}"


@dataclass(frozen=True)
class TierReached(Condition):
    track: str
    tier: str
    toward: str = "subject"
    kind = "tier_reached"

    def evaluate(self, vp: Viewpoint) -> Tri:
        target = vp.who(self.toward)
        if vp.standings is None or not target or vp.holder is None:
            return None
        return vp.standings.tier_reached(vp.holder, target, self.track, self.tier)

    def explain(self) -> str:
        return f"{self.track} tier {self.tier} reached"


@dataclass(frozen=True)
class EventCount(Condition):
    """Committed world events of `event_kind` the holder took part in (with the subject, if set)."""
    event_kind: str
    min: int
    with_subject: bool = True
    within_days: int = 0          # 0 = ever; otherwise only events from the last N days
    kind = "event_count"

    def evaluate(self, vp: Viewpoint) -> Tri:
        people = {p for p in (vp.holder, vp.subject if self.with_subject else None) if p}
        return len(_events(vp, self.event_kind, people, self.within_days)) >= self.min

    def explain(self) -> str:
        recent = f" in the last {self.within_days} days" if self.within_days else ""
        return f"at least {self.min} {self.event_kind} events{recent}"

    def causes(self, vp: Viewpoint) -> tuple[str, ...]:
        people = {p for p in (vp.holder, vp.subject if self.with_subject else None) if p}
        return tuple(e.id for e in _events(vp, self.event_kind, people, self.within_days))


def _events(vp: Viewpoint, event_kind: str, people: set[str], within_days: int) -> list:
    world = vp.model.world
    today = world.day_index(world.minute)
    return [e for e in world.events if e.kind == event_kind and people <= set(e.participants)
            and (not within_days or today - world.day_index(e.minute) < within_days)]


@dataclass(frozen=True)
class Witnessed(Condition):
    """The holder saw it: an event of this kind involving the subject, with the holder a participant or a named witness.

    This is how a third person's behaviour reaches an opinion. Remove the witness and the condition stops holding."""
    event_kind: str
    min: int = 1
    within_days: int = 0
    kind = "witnessed"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if vp.is_truth or not vp.subject:
            return None
        return len(self._seen(vp)) >= self.min

    def _seen(self, vp: Viewpoint) -> list:
        return [e for e in _events(vp, self.event_kind, {vp.subject}, self.within_days)
                if vp.holder in e.participants or vp.holder in (e.payload.get("witnesses") or ())]

    def causes(self, vp: Viewpoint) -> tuple[str, ...]:
        return tuple(e.id for e in self._seen(vp)) if not vp.is_truth and vp.subject else ()

    def explain(self) -> str:
        return f"saw at least {self.min} {self.event_kind} events involving them"


@dataclass(frozen=True)
class Trait(Condition):
    """A temperament dial of a role (the holder by default)."""
    dial: str
    op: str
    value: float
    of: str = "holder"
    kind = "trait"

    def evaluate(self, vp: Viewpoint) -> Tri:
        person = (vp.people or {}).get(vp.who(self.of))
        return None if person is None else OPS[self.op](getattr(person.temperament, self.dial), self.value)

    def explain(self) -> str:
        return f"{self.of} {self.dial} {self.op} {self.value}"


@dataclass(frozen=True)
class StrategyIs(Condition):
    values: tuple[str, ...]
    of: str = "holder"
    kind = "strategy"

    def evaluate(self, vp: Viewpoint) -> Tri:
        person = (vp.people or {}).get(vp.who(self.of))
        return None if person is None else person.strategy in self.values

    def explain(self) -> str:
        return f"{self.of} strategy is {' or '.join(self.values)}"


@dataclass(frozen=True)
class GoalWeight(Condition):
    """The heaviest live goal of this kind the role holds (about `about`, when set) compares to a value."""
    goal_kind: str
    op: str
    value: float
    of: str = "holder"
    about: str = ""
    kind = "goal_weight"

    def evaluate(self, vp: Viewpoint) -> Tri:
        owner = vp.who(self.of)
        person = (vp.people or {}).get(owner)
        if person is None:
            return None
        target = vp.who(self.about) if self.about else None
        weights = [vp.model.goals.weight(owner, g) for g in person.goals
                   if g.kind == self.goal_kind and (target is None or g.target in ("", target))]
        return OPS[self.op](max(weights, default=0.0), self.value)

    def explain(self) -> str:
        return f"{self.of} goal {self.goal_kind} {self.op} {self.value}"


@dataclass(frozen=True)
class HasStance(Condition):
    """A stance already held (earlier rules this turn count): `by` holds `stance` toward `toward`, at least `min` strong."""
    stance: str
    min: float = 0.0
    by: str = "holder"
    toward: str = "subject"
    about: str = ""
    kind = "has_stance"

    def evaluate(self, vp: Viewpoint) -> Tri:
        book = getattr(vp.model, "stances", None)
        if book is None or vp.is_truth:
            return None
        return book.has(vp.who(self.by), self.stance, vp.who(self.toward),
                        vp.who(self.about) if self.about else "", self.min)

    def explain(self) -> str:
        return f"{self.by} {self.stance} {self.toward}"


@dataclass(frozen=True)
class AcquaintanceAtLeast(Condition):
    """The holder knows the player at least this well (days since they met, turns spent together). Residents
    toward one another count as long acquainted: the levels describe getting to know the player."""
    level: str
    kind = "acquaintance_at_least"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if vp.is_truth or not vp.levels:
            return None
        if vp.subject != "player":
            return True
        from backend.app.engine.rules.acquaintance import level_for
        ids = [level.id for level in vp.levels]
        if self.level not in ids:
            return None
        met = vp.model.first_met_day.get(vp.holder)
        if met is None:
            return False
        reached = level_for(vp.levels, vp.model.world.day_index(vp.model.world.minute) - met,
                            vp.model.turns_together.get(vp.holder, 0))
        return reached is not None and ids.index(reached.id) >= ids.index(self.level)

    def explain(self) -> str:
        return f"knows them at least as {self.level}"


@dataclass(frozen=True)
class InCouple(Condition):
    """The role is part of a couple (any formed couple, including ones that have left the house)."""
    of: str = "holder"
    kind = "in_couple"

    def evaluate(self, vp: Viewpoint) -> Tri:
        who = vp.who(self.of)
        return None if not who else any(who in key.split("|") for key in vp.model.npc_couples)

    def explain(self) -> str:
        return f"{self.of} is in a couple"


@dataclass(frozen=True)
class Eligible(Condition):
    """The story's own policy says these two may be drawn to each other (replaces every gender check)."""
    a: str = "holder"
    b: str = "subject"
    kind = "eligible"

    def evaluate(self, vp: Viewpoint) -> Tri:
        first, second = vp.who(self.a), vp.who(self.b)
        if vp.eligible is None or not first or not second:
            return None
        return bool(vp.eligible(first, second))

    def explain(self) -> str:
        return f"{self.a} and {self.b} may be drawn to each other"


@dataclass(frozen=True)
class AgreementCount(Condition):
    activity: str
    status: str
    min: int
    kind = "agreement_count"

    def evaluate(self, vp: Viewpoint) -> Tri:
        people = {p for p in (vp.holder, vp.subject) if p}
        count = sum(1 for a in vp.model.agreements.items
                    if a.status == self.status and (not self.activity or self.activity in a.activity)
                    and people <= {a.proposer, a.counterpart})
        return count >= self.min

    def explain(self) -> str:
        return f"at least {self.min} {self.status} agreements ({self.activity or 'any'})"


@dataclass(frozen=True)
class Knows(Condition):
    """The holder affirms a proposition (by its text) through their own evidence."""
    proposition: str
    kind = "knows"

    def evaluate(self, vp: Viewpoint) -> Tri:
        ledger = vp.model.epistemics
        prop = next((p for p in ledger.propositions if p.text == self.proposition), None)
        if prop is None:
            return False
        if vp.is_truth:
            return True
        belief = next((b for b in ledger.beliefs if b.owner == vp.holder and b.proposition_id == prop.id), None)
        if belief is None:
            return False
        return None if belief.stance == "disputed" else belief.stance == "affirm"

    def explain(self) -> str:
        return f"knows that {self.proposition}"


@dataclass(frozen=True)
class BelievedAttribute(Condition):
    """What the holder believes about the subject from claims they heard; never the truth."""
    key: str
    op: str
    value: Any
    kind = "believed_attribute"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if vp.is_truth or not vp.subject:
            return None
        belief = vp.model.persona.belief(vp.holder, vp.subject, self.key)
        if belief.status != "accepted":
            return None
        if self.op == "in":
            return belief.value.lower() in {str(v).lower() for v in self.value}
        try:
            return OPS[self.op](float(belief.value), float(self.value))
        except (TypeError, ValueError):
            if self.op in ("==", "!="):
                return OPS[self.op](belief.value.lower(), str(self.value).lower())
            return None

    def explain(self) -> str:
        return f"believes {self.key} {self.op} {self.value}"


@dataclass(frozen=True)
class DaysKnown(Condition):
    min: int
    kind = "days_known"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if not vp.subject or vp.holder is None:
            return None
        if vp.subject == "player":
            start = vp.model.first_met_day.get(vp.holder)
            if start is None:
                return False
        else:
            start = 0   # residents have shared the house since the start
        return vp.model.world.day_index(vp.model.world.minute) - start >= self.min

    def explain(self) -> str:
        return f"known for at least {self.min} days"


@dataclass(frozen=True)
class CounterAtLeast(Condition):
    counter: str
    value: int
    kind = "counter_at_least"

    def evaluate(self, vp: Viewpoint) -> Tri:
        return int(getattr(vp.model, "counters", {}).get(self.counter, 0)) >= self.value

    def explain(self) -> str:
        return f"{self.counter} >= {self.value}"


@dataclass(frozen=True)
class Not(Condition):
    inner: Condition
    kind = "not"

    def evaluate(self, vp: Viewpoint) -> Tri:
        value = self.inner.evaluate(vp)
        return None if value is None else not value

    def explain(self) -> str:
        return f"not ({self.inner.explain()})"


@dataclass(frozen=True)
class All(Condition):
    items: tuple[Condition, ...]
    kind = "all"

    def evaluate(self, vp: Viewpoint) -> Tri:
        values = [c.evaluate(vp) for c in self.items]
        if any(v is False for v in values):
            return False
        return None if any(v is None for v in values) else True

    def explain(self) -> str:
        return " and ".join(c.explain() for c in self.items)


@dataclass(frozen=True)
class Any_(Condition):
    items: tuple[Condition, ...]
    kind = "any"

    def evaluate(self, vp: Viewpoint) -> Tri:
        values = [c.evaluate(vp) for c in self.items]
        if any(v is True for v in values):
            return True
        return None if any(v is None for v in values) else False

    def explain(self) -> str:
        return " or ".join(c.explain() for c in self.items)


def parse(raw: Any) -> Condition:
    """Build a condition from story JSON; unknown kinds and bad fields raise ValueError."""
    if not isinstance(raw, dict):
        raise ValueError(f"condition must be an object: {raw!r}")
    kind = raw.get("kind")
    if kind == "feeling":
        dimension = str(raw.get("dimension") or "")
        if dimension not in FEELINGS:
            raise ValueError(f"unknown feeling dimension {dimension!r}")
        return Feeling(dimension, _op(raw), _num(raw, "value"), _role(raw, "toward", "subject"))
    if kind == "standing_at_least":
        return StandingAtLeast(_required(raw, "track"), _num(raw, "value"), _role(raw, "toward", "subject"))
    if kind == "tier_reached":
        return TierReached(_required(raw, "track"), _required(raw, "tier"), _role(raw, "toward", "subject"))
    if kind == "event_count":
        return EventCount(_required(raw, "event_kind"), int(_num(raw, "min", 1)), bool(raw.get("with_subject", True)),
                          int(_num(raw, "within_days", 0)))
    if kind == "witnessed":
        return Witnessed(_required(raw, "event_kind"), int(_num(raw, "min", 1)), int(_num(raw, "within_days", 0)))
    if kind == "trait":
        dial = _required(raw, "dial")
        from backend.app.engine.rules.personality import DIALS
        if dial not in DIALS:
            raise ValueError(f"unknown temperament dial {dial!r}")
        return Trait(dial, _op(raw), _num(raw, "value"), _role(raw, "of", "holder"))
    if kind == "strategy":
        values = raw.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError("strategy needs a non-empty 'values' list")
        from backend.app.engine.rules.personality import STRATEGIES
        bad = [v for v in values if v not in STRATEGIES]
        if bad:
            raise ValueError(f"unknown strategy {bad[0]!r}")
        return StrategyIs(tuple(str(v) for v in values), _role(raw, "of", "holder"))
    if kind == "goal_weight":
        about = str(raw.get("about") or "")
        if about and about not in ROLES:
            raise ValueError(f"unknown role {about!r}")
        return GoalWeight(_required(raw, "goal_kind"), _op(raw), _num(raw, "value"), _role(raw, "of", "holder"), about)
    if kind == "has_stance":
        about = str(raw.get("about") or "")
        if about and about not in ROLES:
            raise ValueError(f"unknown role {about!r}")
        return HasStance(_required(raw, "stance"), _num(raw, "min", 0.0), _role(raw, "by", "holder"),
                         _role(raw, "toward", "subject"), about)
    if kind == "acquaintance_at_least":
        return AcquaintanceAtLeast(_required(raw, "level"))
    if kind == "in_couple":
        return InCouple(_role(raw, "of", "holder"))
    if kind == "eligible":
        return Eligible(_role(raw, "a", "holder"), _role(raw, "b", "subject"))
    if kind == "agreement_count":
        return AgreementCount(str(raw.get("activity") or ""), str(raw.get("status") or "completed"),
                              int(_num(raw, "min", 1)))
    if kind == "knows":
        return Knows(_required(raw, "proposition"))
    if kind == "days_known":
        return DaysKnown(int(_num(raw, "min")))
    if kind == "believed_attribute":
        op = str(raw.get("op") or "==")
        if op != "in" and op not in OPS:
            raise ValueError(f"unknown comparison {op!r}")
        value = raw.get("value")
        if op == "in" and not isinstance(value, list):
            raise ValueError("'in' needs a list value")
        if value is None:
            raise ValueError("believed_attribute needs 'value'")
        return BelievedAttribute(_required(raw, "key"), op, value)
    if kind == "counter_at_least":
        return CounterAtLeast(_required(raw, "counter"), int(_num(raw, "value")))
    if kind == "not":
        return Not(parse(raw.get("condition")))
    if kind in ("all", "any"):
        items = raw.get("conditions")
        if not isinstance(items, list) or not items:
            raise ValueError(f"{kind} needs a non-empty 'conditions' list")
        parsed = tuple(parse(item) for item in items)
        return All(parsed) if kind == "all" else Any_(parsed)
    raise ValueError(f"unknown condition kind {kind!r}")


def _role(raw: dict, key: str, default: str) -> str:
    role = str(raw.get(key) or default)
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}: choose from {list(ROLES)}")
    return role


def _required(raw: dict, key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"condition {raw.get('kind')!r} needs {key!r}")
    return value

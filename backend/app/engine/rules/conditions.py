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


@dataclass(frozen=True)
class Viewpoint:
    """Whose eyes a condition is judged through. holder=None means engine truth."""
    model: Any
    holder: Optional[str]
    subject: Optional[str] = None
    graph: Any = None
    standings: Any = None

    @property
    def is_truth(self) -> bool:
        return self.holder is None


class Condition:
    kind = ""

    def evaluate(self, vp: Viewpoint) -> Tri:
        raise NotImplementedError

    def explain(self) -> str:
        raise NotImplementedError


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
    kind = "feeling"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if vp.is_truth or not vp.subject or vp.graph is None:
            return None
        edge = vp.graph.get_edge(vp.holder, vp.subject)
        return None if edge is None else OPS[self.op](getattr(edge.state, self.dimension), self.value)

    def explain(self) -> str:
        return f"{self.dimension} {self.op} {self.value}"


@dataclass(frozen=True)
class StandingAtLeast(Condition):
    track: str
    value: float
    kind = "standing_at_least"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if vp.standings is None or not vp.subject or vp.holder is None:
            return None
        standing = vp.standings.get(vp.holder, vp.subject, self.track)
        return standing is not None and standing.value >= self.value

    def explain(self) -> str:
        return f"{self.track} standing >= {self.value}"


@dataclass(frozen=True)
class TierReached(Condition):
    track: str
    tier: str
    kind = "tier_reached"

    def evaluate(self, vp: Viewpoint) -> Tri:
        if vp.standings is None or not vp.subject or vp.holder is None:
            return None
        return vp.standings.tier_reached(vp.holder, vp.subject, self.track, self.tier)

    def explain(self) -> str:
        return f"{self.track} tier {self.tier} reached"


@dataclass(frozen=True)
class EventCount(Condition):
    """Committed world events of `event_kind` the holder took part in (with the subject, if set)."""
    event_kind: str
    min: int
    with_subject: bool = True
    kind = "event_count"

    def evaluate(self, vp: Viewpoint) -> Tri:
        people = {p for p in (vp.holder, vp.subject if self.with_subject else None) if p}
        count = sum(1 for e in vp.model.world.events
                    if e.kind == self.event_kind and people <= set(e.participants))
        return count >= self.min

    def explain(self) -> str:
        return f"at least {self.min} {self.event_kind} events"


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
class DaysKnown(Condition):
    min: int
    kind = "days_known"

    def evaluate(self, vp: Viewpoint) -> Tri:
        start = vp.model.first_met_day.get(vp.holder) if vp.subject == "player" else None
        if start is None:
            return None if vp.subject != "player" else False
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
        return Feeling(dimension, _op(raw), _num(raw, "value"))
    if kind == "standing_at_least":
        return StandingAtLeast(_required(raw, "track"), _num(raw, "value"))
    if kind == "tier_reached":
        return TierReached(_required(raw, "track"), _required(raw, "tier"))
    if kind == "event_count":
        return EventCount(_required(raw, "event_kind"), int(_num(raw, "min", 1)), bool(raw.get("with_subject", True)))
    if kind == "agreement_count":
        return AgreementCount(str(raw.get("activity") or ""), str(raw.get("status") or "completed"),
                              int(_num(raw, "min", 1)))
    if kind == "knows":
        return Knows(_required(raw, "proposition"))
    if kind == "days_known":
        return DaysKnown(int(_num(raw, "min")))
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


def _required(raw: dict, key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"condition {raw.get('kind')!r} needs {key!r}")
    return value

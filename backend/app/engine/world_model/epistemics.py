"""Character-local claims and their actual transmission chains.

This ledger records assertions, not canonical world truth. An utterance proves
that words were said; the world event/observation path decides what happened.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Observation:
    id: str
    owner: str
    event_id: str
    channel: str
    details: str
    minute: int

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class Proposition:
    id: str
    text: str
    valid_time: str = ""

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class Assertion:
    id: str
    speaker: str
    proposition_id: str
    stance: str
    minute: int
    utterance_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class Transmission:
    id: str
    assertion_id: str
    sender: str
    recipient: str
    minute: int
    parent_id: str
    root_id: str
    channel: str = "speech"

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass
class Belief:
    owner: str
    proposition_id: str
    support_roots: set[str] = field(default_factory=set)
    opposing_roots: set[str] = field(default_factory=set)

    @property
    def stance(self) -> str:
        if self.support_roots and self.opposing_roots:
            return "disputed"
        if self.support_roots:
            return "affirm"
        if self.opposing_roots:
            return "deny"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {"owner": self.owner, "proposition_id": self.proposition_id,
                "support_roots": sorted(self.support_roots), "opposing_roots": sorted(self.opposing_roots)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Belief":
        return cls(str(raw["owner"]), str(raw["proposition_id"]),
                   set(raw.get("support_roots") or []), set(raw.get("opposing_roots") or []))


@dataclass
class EpistemicLedger:
    observations: list[Observation] = field(default_factory=list)
    propositions: list[Proposition] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    transmissions: list[Transmission] = field(default_factory=list)
    beliefs: list[Belief] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"observations": [o.to_dict() for o in self.observations],
                "propositions": [p.to_dict() for p in self.propositions],
                "assertions": [a.to_dict() for a in self.assertions],
                "transmissions": [t.to_dict() for t in self.transmissions],
                "beliefs": [b.to_dict() for b in self.beliefs]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EpistemicLedger":
        return cls([Observation(**o) for o in raw.get("observations") or []],
                   [Proposition(**p) for p in raw.get("propositions") or []],
                   [Assertion(**a) for a in raw.get("assertions") or []],
                   [Transmission(**t) for t in raw.get("transmissions") or []],
                   [Belief.from_dict(b) for b in raw.get("beliefs") or []])


def observe_event(ledger: EpistemicLedger, owner: str, event_id: str,
                  channel: str, details: str, minute: int) -> Observation:
    if not owner or not event_id or channel not in {"heard", "seen", "read", "participant"}:
        raise ValueError("invalid observation")
    prior = next((o for o in ledger.observations if o.owner == owner and o.event_id == event_id
                  and o.channel == channel), None)
    if prior is not None:
        if prior.details != details:
            raise ValueError("observation replay changed perceived details")
        return prior
    item = Observation(f"O{len(ledger.observations) + 1}", owner, event_id, channel, details, minute)
    ledger.observations.append(item)
    return item


def belief_for(ledger: EpistemicLedger, owner: str, proposition_id: str) -> Belief:
    found = next((b for b in ledger.beliefs if b.owner == owner and b.proposition_id == proposition_id), None)
    return found if found is not None else Belief(owner, proposition_id)


def _learn(ledger: EpistemicLedger, owner: str, assertion: Assertion) -> None:
    belief = belief_for(ledger, owner, assertion.proposition_id)
    if belief not in ledger.beliefs:
        ledger.beliefs.append(belief)
    roots = belief.support_roots if assertion.stance == "affirm" else belief.opposing_roots
    roots.add(assertion.id)


def assert_claim(ledger: EpistemicLedger, speaker: str, text: str, minute: int,
                 stance: str = "affirm", valid_time: str = "", utterance_event_id: str = "") -> Assertion:
    if not speaker or not text.strip() or stance not in {"affirm", "deny"}:
        raise ValueError("invalid assertion")
    proposition = next((p for p in ledger.propositions if p.text == text.strip() and p.valid_time == valid_time), None)
    if proposition is None:
        proposition = Proposition(f"P{len(ledger.propositions) + 1}", text.strip(), valid_time)
        ledger.propositions.append(proposition)
    assertion = Assertion(f"S{len(ledger.assertions) + 1}", speaker, proposition.id, stance,
                          minute, utterance_event_id)
    ledger.assertions.append(assertion)
    _learn(ledger, speaker, assertion)
    return assertion


def transmit(ledger: EpistemicLedger, assertion_id: str, sender: str, recipient: str,
             minute: int, parent_id: str = "", channel: str = "speech") -> Transmission:
    assertion = next(a for a in ledger.assertions if a.id == assertion_id)
    if sender == recipient or not recipient:
        raise ValueError("transmission needs another recipient")
    if parent_id:
        parent = next(t for t in ledger.transmissions if t.id == parent_id)
        if parent.assertion_id != assertion_id or parent.recipient != sender or parent.minute > minute:
            raise ValueError("sender has no valid parent transmission")
    elif sender != assertion.speaker:
        raise ValueError("only original speaker can start this transmission")
    item = Transmission(f"T{len(ledger.transmissions) + 1}", assertion_id, sender, recipient,
                        minute, parent_id, assertion.id, channel)
    ledger.transmissions.append(item)
    _learn(ledger, recipient, assertion)
    return item

"""Authoritative invitations and scheduled agreements.

Dialogue can suggest an agreement, but only participant decisions change its
status. A memory of a promise is a recall projection, never the agreement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

TERMINAL = frozenset({"declined", "cancelled", "completed", "breached", "expired", "superseded"})


@dataclass
class Agreement:
    id: str
    proposer: str
    counterpart: str
    activity: str
    due: Optional[int]
    created: int
    status: str = "proposed"
    decisions: dict[str, str] = field(default_factory=dict)
    source_event_id: str = ""
    outcome_event_id: str = ""
    supersedes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "proposer": self.proposer, "counterpart": self.counterpart,
                "activity": self.activity, "due": self.due, "created": self.created,
                "status": self.status, "decisions": dict(self.decisions),
                "source_event_id": self.source_event_id, "outcome_event_id": self.outcome_event_id,
                "supersedes": self.supersedes}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Agreement":
        return cls(str(raw["id"]), str(raw["proposer"]), str(raw["counterpart"]),
                   str(raw["activity"]), raw.get("due"), int(raw.get("created") or 0),
                   str(raw.get("status") or "proposed"), dict(raw.get("decisions") or {}),
                   str(raw.get("source_event_id") or ""), str(raw.get("outcome_event_id") or ""),
                   str(raw.get("supersedes") or ""))


@dataclass
class AgreementBook:
    items: list[Agreement] = field(default_factory=list)
    counter: int = 0

    def get(self, agreement_id: str) -> Agreement:
        return next(item for item in self.items if item.id == agreement_id)

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items], "counter": self.counter}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AgreementBook":
        items = [Agreement.from_dict(item) for item in raw.get("items") or []]
        return cls(items, max(int(raw.get("counter") or 0), len(items)))


def propose(book: AgreementBook, proposer: str, counterpart: str, activity: str,
            due: Optional[int], minute: int, source_event_id: str = "", supersedes: str = "") -> Agreement:
    if not proposer or not counterpart or proposer == counterpart or not activity.strip():
        raise ValueError("an agreement needs two distinct people and an activity")
    if due is not None and due < minute:
        raise ValueError("an agreement cannot be due in the past")
    if supersedes and book.get(supersedes).status != "accepted":
        raise ValueError("only an accepted agreement can be rescheduled")
    book.counter += 1
    agreement = Agreement(f"A{book.counter}", proposer, counterpart, activity.strip(), due, minute,
                          decisions={proposer: "accepted", counterpart: "pending"},
                          source_event_id=source_event_id, supersedes=supersedes)
    book.items.append(agreement)
    return agreement


def record_unilateral_promise(book: AgreementBook, owner: str, counterpart: str, activity: str,
                              due: Optional[int], minute: int) -> Agreement:
    """The promiser is bound; the other party is informed, not made to consent."""
    item = propose(book, owner, counterpart, activity, due, minute)
    item.decisions[counterpart] = "informed"
    item.status = "accepted"
    return item


def decide(book: AgreementBook, agreement_id: str, actor: str, decision: str, minute: int) -> Agreement:
    item = book.get(agreement_id)
    if item.status != "proposed" or actor not in item.decisions or decision not in {"accepted", "declined"}:
        raise ValueError("invalid or stale agreement decision")
    if minute < item.created:
        raise ValueError("decision predates proposal")
    item.decisions[actor] = decision
    if decision == "declined":
        item.status = "declined"
    elif all(value == "accepted" for value in item.decisions.values()):
        item.status = "accepted"
        if item.supersedes:
            book.get(item.supersedes).status = "superseded"
    return item


def reschedule(book: AgreementBook, agreement_id: str, proposer: str, due: int, minute: int) -> Agreement:
    prior = book.get(agreement_id)
    if proposer not in prior.decisions:
        raise ValueError("only a participant can reschedule")
    counterpart = prior.counterpart if proposer == prior.proposer else prior.proposer
    return propose(book, proposer, counterpart, prior.activity, due, minute, supersedes=prior.id)


def resolve(book: AgreementBook, agreement_id: str, outcome: str, minute: int,
            evidence_event_id: str = "") -> Agreement:
    item = book.get(agreement_id)
    if item.status != "accepted" or outcome not in {"completed", "breached", "cancelled", "expired"}:
        raise ValueError("only an accepted agreement can resolve")
    if outcome in {"completed", "breached"} and not evidence_event_id:
        raise ValueError("completion or breach requires evidence")
    if minute < item.created:
        raise ValueError("outcome predates proposal")
    item.status, item.outcome_event_id = outcome, evidence_event_id
    return item


def conflicts(book: AgreementBook, actor: str, due: int) -> list[Agreement]:
    return [item for item in book.items if item.status == "accepted" and item.due == due
            and item.decisions.get(actor) == "accepted"]

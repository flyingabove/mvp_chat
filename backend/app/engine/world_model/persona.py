"""What people have said about themselves, and what each listener now believes.

Every self-claim is immutable history with its audience. A listener's belief
comes only from claims they heard: consistent claims are accepted, an
explicit correction replaces the earlier value, and incompatible claims
without a correction leave the belief disputed (unknown). A dispute is not
proof of lying; it raises suspicion according to the listener's skepticism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SelfClaim:
    speaker: str
    key: str
    value: str
    audience: tuple[str, ...]
    minute: int
    turn: int
    event_id: str = ""
    correction: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"speaker": self.speaker, "key": self.key, "value": self.value, "audience": list(self.audience),
                "minute": self.minute, "turn": self.turn, "event_id": self.event_id, "correction": self.correction}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SelfClaim":
        return cls(str(raw["speaker"]), str(raw["key"]), str(raw["value"]), tuple(raw.get("audience") or ()),
                   int(raw.get("minute") or 0), int(raw.get("turn") or 0), str(raw.get("event_id") or ""),
                   bool(raw.get("correction")))


@dataclass(frozen=True)
class ClaimBelief:
    status: str                 # unknown | accepted | disputed
    value: Optional[str] = None
    corrected: bool = False


def _same(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


@dataclass
class PersonaBook:
    claims: list[SelfClaim] = field(default_factory=list)

    def claim(self, claim: SelfClaim) -> Optional[SelfClaim]:
        """Record a claim once (same speaker, key, value, turn); returns None for a repeat."""
        for prior in self.claims:
            if (prior.speaker, prior.key, prior.turn) == (claim.speaker, claim.key, claim.turn) \
                    and _same(prior.value, claim.value):
                return None
        self.claims.append(claim)
        return claim

    def first(self, speaker: str, key: str) -> Optional[SelfClaim]:
        return next((c for c in self.claims if c.speaker == speaker and c.key == key), None)

    def heard_by(self, listener: str, speaker: str, key: str) -> list[SelfClaim]:
        return [c for c in self.claims if c.speaker == speaker and c.key == key and listener in c.audience]

    def belief(self, listener: str, speaker: str, key: str) -> ClaimBelief:
        heard = self.heard_by(listener, speaker, key)
        if not heard:
            return ClaimBelief("unknown")
        current = heard[0].value
        corrected = False
        for claim in heard[1:]:
            if _same(claim.value, current):
                continue
            if claim.correction:
                current, corrected = claim.value, True
            else:
                return ClaimBelief("disputed")
        return ClaimBelief("accepted", current, corrected)

    def to_dict(self) -> dict[str, Any]:
        return {"claims": [c.to_dict() for c in self.claims]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PersonaBook":
        return cls([SelfClaim.from_dict(c) for c in raw.get("claims") or []])

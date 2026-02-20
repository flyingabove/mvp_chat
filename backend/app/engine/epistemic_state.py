from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class EpistemicStatus(str, Enum):
    ASSERTED = "asserted"
    CONTESTED = "contested"
    RESOLVED = "resolved"


@dataclass
class EpistemicEntry:
    """Base record for epistemic elements (facts, claims, observations)."""

    id: str
    content: str
    subject: Optional[str] = None
    object: Optional[str] = None
    source: str = "system"
    timestamp_minute: Optional[int] = None
    location_ref: Optional[str] = None
    confidence: float = 1.0
    provenance: str = "system"
    known_by: List[str] = field(default_factory=list)
    not_known_by: List[str] = field(default_factory=list)
    maybe_known_by: List[str] = field(default_factory=list)
    status: EpistemicStatus = EpistemicStatus.ASSERTED
    resolution: Optional[str] = None

    def __post_init__(self):
        # Confidence stays within [0, 1].
        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError):
            self.confidence = 0.0
        self.confidence = max(0.0, min(1.0, self.confidence))

    def contested_with(self, other: "EpistemicEntry") -> "EpistemicEntry":
        """Mark both entries as contested (used when claims conflict)."""
        self.status = EpistemicStatus.CONTESTED
        other.status = EpistemicStatus.CONTESTED
        return self

    def resolve_conflict(self, resolution: str, *, status: EpistemicStatus = EpistemicStatus.RESOLVED) -> "EpistemicEntry":
        """Record how this entry was resolved (e.g., confession, evidence)."""
        self.status = status
        self.resolution = resolution
        return self

    def as_prompt_snippet(self) -> str:
        """Human-friendly summary for prompts/debug panels."""
        labels: List[str] = []
        if self.status:
            labels.append(f"status={self.status.value}")
        if self.provenance:
            labels.append(f"prov={self.provenance}")
        labels.append(f"conf={self.confidence:.2f}")
        if self.location_ref:
            labels.append(f"loc={self.location_ref}")
        if self.timestamp_minute is not None:
            labels.append(f"t={self.timestamp_minute}")
        if self.resolution:
            labels.append(f"resolution={self.resolution}")

        suffix = f" ({' | '.join(labels)})" if labels else ""
        return f"{self.content}{suffix}"


@dataclass
class EpistemicFact(EpistemicEntry):
    """Canonical fact tied to truth graph/world state."""


@dataclass
class EpistemicClaim(EpistemicEntry):
    """Claim made by a speaker (player/NPC/system)."""


@dataclass
class Observation(EpistemicEntry):
    """Player or NPC observation (what was seen/heard)."""


@dataclass
class BeliefState:
    """Belief graph/log for a specific character."""

    character_id: str
    claims: List[EpistemicClaim] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)

    def record_observation(
        self,
        *,
        id: str,
        content: str,
        timestamp_minute: Optional[int] = None,
        location_ref: Optional[str] = None,
        subject: Optional[str] = None,
        object: Optional[str] = None,
        source: str = "player",
        provenance: str = "observed",
        confidence: float = 1.0,
    ) -> Observation:
        """Append an observation to this character's belief log."""
        obs = Observation(
            id=id,
            content=content,
            subject=subject,
            object=object,
            source=source,
            timestamp_minute=timestamp_minute,
            location_ref=location_ref,
            confidence=confidence,
            provenance=provenance,
        )
        self.observations.append(obs)
        return obs

    def add_claim(self, claim: EpistemicClaim) -> EpistemicClaim:
        """Append a claim to this character's belief log."""
        self.claims.append(claim)
        return claim

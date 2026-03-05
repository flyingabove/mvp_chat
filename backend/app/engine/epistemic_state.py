from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from backend.app.engine.knowledge_chunks import KnowledgeChunk


class EpistemicStatus(str, Enum):
    ASSERTED = "asserted"
    CONTESTED = "contested"
    RESOLVED = "resolved"


# Backward-compat aliases — code that imports these names still works.
# All three map to KnowledgeChunk; use the `kind` field to distinguish:
#   kind="fact"        → formerly EpistemicFact
#   kind="claim"       → formerly EpistemicClaim
#   kind="observation" → formerly Observation
EpistemicEntry = KnowledgeChunk
EpistemicFact = KnowledgeChunk
EpistemicClaim = KnowledgeChunk
Observation = KnowledgeChunk


@dataclass
class BeliefState:
    """Belief graph/log for a specific character."""

    character_id: str
    claims: List[KnowledgeChunk] = field(default_factory=list)
    observations: List[KnowledgeChunk] = field(default_factory=list)

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
    ) -> KnowledgeChunk:
        """Append an observation to this character's belief log."""
        obs = KnowledgeChunk(
            id=id,
            content=content,
            kind="observation",
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

    def add_claim(self, claim: KnowledgeChunk) -> KnowledgeChunk:
        """Append a claim to this character's belief log."""
        self.claims.append(claim)
        return claim

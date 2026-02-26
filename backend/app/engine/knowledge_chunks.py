from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class KnowledgeChunk:
    """
    Universal knowledge unit. Replaces the former EpistemicEntry / EpistemicFact /
    EpistemicClaim / Observation hierarchy. Used by:
    - Canonical truth layer (facts from epistemic_seed)
    - Belief layer (per-character claims / observations)
    - FAISS / BM25 retrieval (tier / certainty fields)

    Fields are a superset of both the old EpistemicEntry schema and the old
    KnowledgeChunk schema. Optional fields default to neutral values so that
    both old-style and new-style construction work without changes.
    """

    # --- Identity ---
    id: str

    # --- Content (primary text body) ---
    # `text` is the canonical field used by FAISS/BM25 retrieval.
    # `content` is the legacy name used by the epistemic layer (EpistemicEntry).
    # __post_init__ syncs them: whichever is non-empty wins; if both, `text` wins.
    text: str = ""
    content: str = ""

    # --- Retrieval tier / display certainty ---
    tier: str = ""          # e.g. "CANONICAL_CORE", "SUBJECTIVE_BELIEF", "RETRIEVED_MEMORY"
    source: str = "system"  # origin identifier (e.g. "system", character key)
    certainty: str = ""     # human-readable certainty label for display ("high"/"mixed"/"low")

    # --- Visibility ---
    known_by: List[str] = field(default_factory=list)
    not_known_by: List[str] = field(default_factory=list)
    maybe_known_by: List[str] = field(default_factory=list)

    # --- Epistemic metadata (from former EpistemicEntry) ---
    kind: Optional[str] = None          # "fact" | "claim" | "observation" | None
    subject: Optional[str] = None       # who/what this is about
    object: Optional[str] = None        # target entity
    timestamp_minute: Optional[int] = None
    location_ref: Optional[str] = None
    confidence: float = 1.0             # 0.0–1.0
    provenance: str = "system"          # who asserted this (character key or "system")
    status: str = "asserted"            # "asserted" | "contested" | "resolved"
    resolution: Optional[str] = None    # how a contested entry was resolved

    def __post_init__(self) -> None:
        # Sync content ↔ text: text takes priority; fall back to content.
        if self.text and not self.content:
            self.content = self.text
        elif self.content and not self.text:
            self.text = self.content
        # Clamp confidence to [0, 1].
        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError):
            self.confidence = 0.0
        self.confidence = max(0.0, min(1.0, self.confidence))

    # --- Methods ported from EpistemicEntry ---

    def contested_with(self, other: "KnowledgeChunk") -> "KnowledgeChunk":
        """Mark both entries as contested (used when claims conflict)."""
        self.status = "contested"
        other.status = "contested"
        return self

    def resolve_conflict(self, resolution: str, *, status: str = "resolved") -> "KnowledgeChunk":
        """Record how this entry was resolved (e.g., confession, evidence)."""
        self.status = status
        self.resolution = resolution
        return self

    def as_prompt_snippet(self) -> str:
        """Human-friendly summary for prompts/debug panels."""
        labels: List[str] = []
        if self.status:
            labels.append(f"status={self.status}")
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
        body = self.text or self.content
        return f"{body}{suffix}"


def normalize_party_token(value: str) -> str:
    token = (value or "").strip().lower().replace(" ", "_")
    if token in {"all", "everyone", "all_characters", "allcharacters", "common_knowledge"}:
        return "all_characters"
    return token


def normalize_parties(values: list | None) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values or []:
        token = normalize_party_token(str(v))
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out

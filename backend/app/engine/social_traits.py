"""Generic "evolving trait" primitive (Six Strangers audit Phase 3: "Social
life"): a labeled current value plus an append-only, provenanced history of
why/when it changed.

Genre-agnostic on purpose. This same class serves two instantiations:
  - A character's own persistent goal/motive (node-scoped, singular, e.g.
    Character.goal). An ensemble drama authors this from a "motive" string;
    a mystery story authors it identically from the same field.
  - A character's disposition toward one specific other character
    (edge-scoped, e.g. RelationshipEdge.disposition — "in love with X",
    "growing suspicious of Y"). A mystery story's "tells"-driven suspicion
    arc and an ensemble drama's romance arc both produce disposition
    changes through this same container; nothing in this module knows or
    cares which genre is calling it.

Reuses KnowledgeChunk (backend/app/engine/knowledge_chunks.py) as the
history-entry shape rather than inventing a second "timestamped,
provenanced, confidence-scored claim" record type - the engine already has
one and it fits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.engine.knowledge_chunks import KnowledgeChunk


@dataclass
class EvolvingTrait:
    """Current value + full history of a character's goal or disposition.

    kind: free string discriminator ("goal" | "disposition"). Purely
        informational for serialization/debugging - no branching logic
        anywhere keys off it.
    subject_id: character key this trait belongs to.
    target_id: empty for a node-scoped goal (not about anyone in
        particular); the other character's key for an edge-scoped
        disposition.
    current: the present-day label, e.g. "win back Mara's trust" or
        "guardedly warming up to Theo". Empty string is a valid, common
        state ("no trait established yet") and MUST render as nothing
        wherever this is surfaced in a prompt.
    confidence: 0..1, how firmly established `current` is.
    history: append-only, oldest first. Never mutated or trimmed once
        written - rewriting history defeats the point of an auditable
        trail. Each entry's `.content` is the value at that time,
        `.source` is "author" | "extractor" | "system", `.timestamp_minute`
        is the game minute, `.confidence` is that entry's own confidence,
        `.provenance` is a short human-readable reason for the change.
    """
    kind: str
    subject_id: str
    target_id: str = ""
    current: str = ""
    confidence: float = 0.0
    history: List[KnowledgeChunk] = field(default_factory=list)

    def set_initial(
        self, value: str, *, minute: int = 0, source: str = "author", confidence: float = 1.0,
    ) -> bool:
        """Seed the very first value (from story JSON or a default). No-op
        (returns False) if value is blank. Returns True if seeded."""
        value = (value or "").strip()
        if not value:
            return False
        self.current = value
        self.confidence = max(0.0, min(1.0, confidence))
        self.history.append(KnowledgeChunk(
            id=f"{self.kind}:{self.subject_id}:{self.target_id}:{len(self.history)}",
            content=value,
            source=source,
            confidence=self.confidence,
            timestamp_minute=minute,
            provenance=source,
        ))
        return True

    def propose_change(
        self, value: str, *, minute: int, reason: str, confidence: float,
        entry_id: str, source: str = "extractor",
    ) -> bool:
        """Append a new current value with full provenance. Never removes or
        edits prior entries. Returns False (no-op) when:
          - `value` is blank, or
          - `entry_id` already exists in history (idempotency guard - a
            retried turn with the same turn-keyed id is a safe no-op), or
          - `value` is identical to the current value.
        Returns True when a new history entry was appended and `current`
        was updated.
        """
        value = (value or "").strip()
        if not value:
            return False
        if any(e.id == entry_id for e in self.history):
            return False
        if value == self.current:
            return False
        self.history.append(KnowledgeChunk(
            id=entry_id,
            content=value,
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            timestamp_minute=minute,
            provenance=reason,
        ))
        self.current = value
        self.confidence = max(0.0, min(1.0, confidence))
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "subject_id": self.subject_id,
            "target_id": self.target_id,
            "current": self.current,
            "confidence": self.confidence,
            "history": [
                {
                    "id": h.id,
                    "content": h.content,
                    "source": h.source,
                    "confidence": h.confidence,
                    "timestamp_minute": h.timestamp_minute,
                    "provenance": h.provenance,
                }
                for h in self.history
            ],
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EvolvingTrait":
        data = data or {}
        history: List[KnowledgeChunk] = []
        for h in (data.get("history") or []):
            if not isinstance(h, dict):
                continue
            history.append(KnowledgeChunk(
                id=str(h.get("id") or ""),
                content=str(h.get("content") or ""),
                source=str(h.get("source") or "system"),
                confidence=float(h.get("confidence") or 0.0),
                timestamp_minute=h.get("timestamp_minute"),
                provenance=str(h.get("provenance") or ""),
            ))
        return cls(
            kind=str(data.get("kind") or ""),
            subject_id=str(data.get("subject_id") or ""),
            target_id=str(data.get("target_id") or ""),
            current=str(data.get("current") or ""),
            confidence=float(data.get("confidence") or 0.0),
            history=history,
        )

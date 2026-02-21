# backend/app/engine/character_graph.py
"""
Character relationship graph — multi-dimensional directed edges between characters.

Each edge carries trust/fear/affection/suspicion state, a typed relationship label,
and an optional human-readable context string for prompt injection.

Adapted from the retired story_schema_v2.py RelationshipState/Edge/Graph into
a standalone production module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RelationshipType(str, Enum):
    FRIEND = "FRIEND"
    ENEMY = "ENEMY"
    FAMILY = "FAMILY"
    LOVER = "LOVER"
    EMPLOYER = "EMPLOYER"
    EMPLOYEE = "EMPLOYEE"
    SUSPECT = "SUSPECT"
    VICTIM = "VICTIM"
    WITNESS = "WITNESS"
    OTHER = "OTHER"


@dataclass
class RelationshipState:
    """Multi-dimensional relationship state between two characters."""
    trust: float = 0.0       # -1..1  How much A trusts B
    fear: float = 0.0        # 0..1   How afraid A is of B
    affection: float = 0.0   # -1..1  Emotional warmth (negative = resentment)
    suspicion: float = 0.0   # 0..1   How much A suspects B of wrongdoing

    def __post_init__(self) -> None:
        self._clamp()

    def _clamp(self) -> None:
        self.trust = max(-1.0, min(1.0, float(self.trust)))
        self.fear = max(0.0, min(1.0, float(self.fear)))
        self.affection = max(-1.0, min(1.0, float(self.affection)))
        self.suspicion = max(0.0, min(1.0, float(self.suspicion)))

    def collapse(self) -> int:
        """Map multi-dimensional state to legacy integer score (-5..+5).

        Formula: weighted sum of affection (dominant) and trust, reduced by
        fear and suspicion, then scaled to the -5..+5 range.
        """
        raw = (self.affection * 0.5 + self.trust * 0.3
               - self.fear * 0.1 - self.suspicion * 0.1)
        return max(-5, min(5, round(raw * 5)))

    def apply_delta(self, **kwargs: float) -> None:
        """Apply incremental changes to dimensions and re-clamp."""
        for key, delta in kwargs.items():
            if hasattr(self, key) and key not in ("_clamp",):
                old = getattr(self, key)
                if isinstance(old, (int, float)):
                    setattr(self, key, old + delta)
        self._clamp()

    @classmethod
    def from_dict(cls, d: Dict[str, Any] | None) -> "RelationshipState":
        d = d or {}
        return cls(
            trust=float(d.get("trust", 0.0)),
            fear=float(d.get("fear", 0.0)),
            affection=float(d.get("affection", 0.0)),
            suspicion=float(d.get("suspicion", 0.0)),
        )


@dataclass
class RelationshipEdge:
    """Directed edge from one character to another."""
    id: str
    from_id: str
    to_id: str
    type: RelationshipType = RelationshipType.OTHER
    state: RelationshipState = field(default_factory=RelationshipState)
    label: str = ""           # Human-readable context for prompt injection
    symmetric: bool = False

    @classmethod
    def from_dict(cls, edge_id: str, d: Dict[str, Any] | None) -> "RelationshipEdge":
        d = d or {}
        type_raw = str(d.get("type", "OTHER")).upper()
        try:
            rel_type = RelationshipType(type_raw)
        except ValueError:
            rel_type = RelationshipType.OTHER
        return cls(
            id=edge_id,
            from_id=str(d.get("from_id") or d.get("from", "")),
            to_id=str(d.get("to_id") or d.get("to", "")),
            type=rel_type,
            state=RelationshipState.from_dict(d.get("state")),
            label=str(d.get("label", "")),
            symmetric=bool(d.get("symmetric", False)),
        )


@dataclass
class CharacterGraph:
    """Directed graph of character-to-character relationships."""
    edges: Dict[str, RelationshipEdge] = field(default_factory=dict)

    def get_edges_from(self, character_id: str) -> List[RelationshipEdge]:
        """All edges originating from a given character."""
        return [e for e in self.edges.values() if e.from_id == character_id]

    def get_edge(self, from_id: str, to_id: str) -> Optional[RelationshipEdge]:
        """Find a specific edge, respecting symmetric edges."""
        for e in self.edges.values():
            if e.from_id == from_id and e.to_id == to_id:
                return e
            if e.symmetric and e.from_id == to_id and e.to_id == from_id:
                return e
        return None

    def apply_rel_delta(self, from_id: str, to_id: str, rel_delta: int) -> None:
        """Phase 1 backward compat: map legacy rel_delta (-1/0/+1) to affection."""
        edge = self.get_edge(from_id, to_id)
        if edge is None:
            return
        # Map ±1 integer to ±0.1 affection delta
        edge.state.apply_delta(affection=rel_delta * 0.1)

    def format_for_prompt(
        self,
        speaker_id: str,
        characters: dict,
        active_characters: set[str] | None = None,
    ) -> str:
        """Build the relationship context section for the system prompt.

        Args:
            speaker_id: the character whose perspective we're building for
            characters: dict of key -> CharacterState (or any object with .name)
            active_characters: if provided, only include edges targeting these keys

        Returns:
            Formatted string for prompt injection, or empty string if no edges.
        """
        edges = self.get_edges_from(speaker_id)
        if not edges:
            return ""

        # Filter to active characters if specified
        if active_characters is not None:
            edges = [e for e in edges if e.to_id in active_characters]
            if not edges:
                return ""

        # Cap at 6 edges for prompt size control
        edges = edges[:6]

        lines = []
        for e in edges:
            # Resolve display name
            target = characters.get(e.to_id)
            name = getattr(target, "name", None) or e.to_id
            if e.to_id == "player":
                name = "The Player"

            type_label = e.type.value.lower().replace("_", " ")
            s = e.state
            state_str = f"Trust: {s.trust:+.1f}, Fear: {s.fear:.1f}, Affection: {s.affection:+.1f}, Suspicion: {s.suspicion:.1f}"

            if e.to_id == "player":
                label_name = f"{name} ({e.to_id})"
            else:
                label_name = f"{name} ({e.to_id})"

            line = f"- {label_name} ({type_label}): {state_str}"
            if e.label:
                line += f"\n  {e.label}"
            lines.append(line)

        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: Dict[str, Any] | None) -> "CharacterGraph":
        """Parse from story JSON relationships section.

        Supports both dict-keyed edges and list-of-dicts with 'id' field.
        """
        if not d:
            return cls()
        raw_edges = d.get("edges") or {}
        if isinstance(raw_edges, list):
            edges = {}
            for item in raw_edges:
                eid = str(item.get("id", f"edge_{len(edges)}"))
                edges[eid] = RelationshipEdge.from_dict(eid, item)
        else:
            edges = {
                eid: RelationshipEdge.from_dict(eid, edata)
                for eid, edata in raw_edges.items()
            }
        return cls(edges=edges)

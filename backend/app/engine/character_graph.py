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


_TENTHS = [round(-1.0 + 0.1 * i, 1) for i in range(21)]

_TRUST_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "betrayed", "treacherous", "hostile", "distrustful", "wary", "skeptical", "guarded", "reserved", "cautious", "unsure", "neutral", "open", "receptive", "cooperative", "confident", "reliant", "trusting", "devoted", "steadfast", "unshakable", "absolute",
    ])
}

_AFFECTION_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "hateful", "resentful", "cold", "bitter", "hostile", "distant", "aloof", "detached", "dry", "reserved", "neutral", "warm", "friendly", "fond", "caring", "attached", "affectionate", "devoted", "tender", "adoring", "deeply_bonded",
    ])
}

_FEAR_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "fearless", "calm", "steady", "composed", "unfazed", "alert", "watchful", "uneasy", "nervous", "tense", "guarded", "anxious", "shaken", "alarmed", "frightened", "panicked", "terrified", "horrified", "petrified", "overwhelmed", "paralyzed",
    ])
}

_SUSPICION_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "fully_trusting", "trusting", "accepting", "open-minded", "unconcerned", "relaxed", "attentive", "questioning", "doubtful", "uncertain", "guarded", "skeptical", "wary", "dubious", "suspicious", "highly_suspicious", "convinced", "accusatory", "paranoid", "hypervigilant", "obsessed",
    ])
}


def _clamp_unit(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _round_tenth(value: float) -> float:
    return round(_clamp_unit(value), 1)


def _normalize_zero_to_one(value: float) -> float:
    v = max(0.0, min(1.0, float(value)))
    return _round_tenth(v * 2.0 - 1.0)


def _word_from_scale(scale: dict[float, str], normalized_value: float) -> str:
    return scale[_round_tenth(normalized_value)]


def _stance_sentence(*, trust_n: float, fear_n: float, affection_n: float, suspicion_n: float) -> str:
    cooperative = trust_n >= 0.3 and affection_n >= 0.2 and fear_n <= 0.1 and suspicion_n <= 0.1
    defensive = fear_n >= 0.3 or suspicion_n >= 0.3
    hostile = trust_n <= -0.4 and affection_n <= -0.4

    if cooperative:
        return "Behavior tendency: cooperative and candid, likely to engage and share."
    if hostile and defensive:
        return "Behavior tendency: defensive-hostile, likely to resist, deflect, or confront."
    if hostile:
        return "Behavior tendency: hostile distance, likely to push back and withhold."
    if defensive:
        return "Behavior tendency: guarded defense, likely to hedge and reveal selectively."
    return "Behavior tendency: neutral-watchful, likely to respond cautiously without full openness."


def describe_relationship_state(state: "RelationshipState") -> dict[str, str | float]:
    trust_n = _round_tenth(state.trust)
    affection_n = _round_tenth(state.affection)
    fear_n = _normalize_zero_to_one(state.fear)
    suspicion_n = _normalize_zero_to_one(state.suspicion)

    trust_w = _word_from_scale(_TRUST_WORDS, trust_n)
    fear_w = _word_from_scale(_FEAR_WORDS, fear_n)
    affection_w = _word_from_scale(_AFFECTION_WORDS, affection_n)
    suspicion_w = _word_from_scale(_SUSPICION_WORDS, suspicion_n)

    summary = (
        f"Trust={trust_w} ({trust_n:+.1f}); "
        f"Fear={fear_w} ({fear_n:+.1f}); "
        f"Affection={affection_w} ({affection_n:+.1f}); "
        f"Suspicion={suspicion_w} ({suspicion_n:+.1f})."
    )

    stance = _stance_sentence(
        trust_n=trust_n,
        fear_n=fear_n,
        affection_n=affection_n,
        suspicion_n=suspicion_n,
    )

    return {
        "trust_normalized": trust_n,
        "fear_normalized": fear_n,
        "affection_normalized": affection_n,
        "suspicion_normalized": suspicion_n,
        "trust_word": trust_w,
        "fear_word": fear_w,
        "affection_word": affection_w,
        "suspicion_word": suspicion_w,
        "summary": summary,
        "stance": stance,
    }


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
            described = describe_relationship_state(e.state)

            if e.to_id == "player":
                label_name = f"{name} ({e.to_id})"
            else:
                label_name = f"{name} ({e.to_id})"

            line = f"- {label_name} ({type_label}): {described['summary']}"
            line += f"\n  {described['stance']}"
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

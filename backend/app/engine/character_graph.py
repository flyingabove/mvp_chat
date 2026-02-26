# backend/app/engine/character_graph.py
"""
Character relationship graph — directed edges between character nodes.

CHARACTER TYPES
───────────────
Every participant in the game is a Character with a CharacterType:

  USER      — The human player. Always key="player". Auto-created at game init;
               not defined in story JSON. Has relationship edges to all authored NPCs.
  MAIN      — The focal NPC of the session (is_main=True in story JSON). The character
               the player primarily interacts with. Has a full knowledge/lore bundle.
  CANONICAL — Authored NPC with a defined story role and optional knowledge bundle.
               Fully scripted backstory, motivations, and relationships.
  NPC       — Incidental or emergent character. May be introduced by the LLM in
               dialogue. No authored knowledge bundle; exists at runtime only.

GRAPH DESIGN
────────────
CharacterGraph stores both character nodes (Dict[key, Character]) and directed
relationship edges (Dict["from->to", RelationshipEdge]). Exactly one edge per
ordered (from_id, to_id) pair is enforced via canonical key.

EDGE FIELDS
───────────
Each RelationshipEdge tracks:
  state        — four numeric dimensions (trust, fear, affection, suspicion)
  label        — static authored context, never changes ("former manager, dispute")
  narrative    — dynamic runtime note, replaced on each update by the LLM
  narrative_log — append-only session history of all narrative notes

QUERY INTERFACE
───────────────
All query methods return RelationshipEdge or List[RelationshipEdge]:

  get_character(key)              → Character node, or None
  get_edge(a, b)                  → RelationshipEdge from a to b, or None
  get_edges_from(a)               → List[RelationshipEdge] outgoing from a
  get_edges_to(a)                 → List[RelationshipEdge] incoming to a
  get_all_relationships(a)        → List[RelationshipEdge] involving a (in or out)
  get_room_relationships(ids)     → List[RelationshipEdge] between any pair in ids

ROOM SCENARIO
─────────────
CharacterGraph is a pure data layer. It returns edges; it never generates prose.
All prose generation happens in prompt_builder.py.

When a player enters a location with IU and Steve present:

    # Step 1 — query raw data from the graph (pure data, no prose)
    edges = graph.get_room_relationships({"player", "iu", "steve"})
    # → List[RelationshipEdge]: iu→player, iu→steve, steve→player, steve→iu, ...

    # Step 2 — generate prose in prompt_builder (not in the graph)
    section = _room_relationship_section(state, {"player", "iu", "steve"})
    # → "IU and Steve regard each other with mutual suspicion. IU is drawn to
    #    the player, who keeps their distance. Steve is visibly afraid of IU."

prose generation functions (in prompt_builder.py):
  _summarize_room_relationships(edges, characters) → str
  _room_relationship_section(state, room_character_ids) → str
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.engine.state import Character


# ──────────────────────────────────────────────────────────────────────────────
# Word-scale mappings for human-readable relationship descriptions
# ──────────────────────────────────────────────────────────────────────────────

_TENTHS = [round(-1.0 + 0.1 * i, 1) for i in range(21)]

_TRUST_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "betrayed", "treacherous", "hostile", "distrustful", "wary", "skeptical",
        "guarded", "reserved", "cautious", "unsure", "neutral", "open", "receptive",
        "cooperative", "confident", "reliant", "trusting", "devoted", "steadfast",
        "unshakable", "absolute",
    ])
}

_AFFECTION_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "hateful", "resentful", "cold", "bitter", "hostile", "distant", "aloof",
        "detached", "dry", "reserved", "neutral", "warm", "friendly", "fond",
        "caring", "attached", "affectionate", "devoted", "tender", "adoring",
        "deeply_bonded",
    ])
}

_FEAR_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "fearless", "calm", "steady", "composed", "unfazed", "alert", "watchful",
        "uneasy", "nervous", "tense", "guarded", "anxious", "shaken", "alarmed",
        "frightened", "panicked", "terrified", "horrified", "petrified",
        "overwhelmed", "paralyzed",
    ])
}

_SUSPICION_WORDS = {
    t: w for t, w in zip(_TENTHS, [
        "fully_trusting", "trusting", "accepting", "open-minded", "unconcerned",
        "relaxed", "attentive", "questioning", "doubtful", "uncertain", "guarded",
        "skeptical", "wary", "dubious", "suspicious", "highly_suspicious",
        "convinced", "accusatory", "paranoid", "hypervigilant", "obsessed",
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
        f"Trust is {trust_w}; "
        f"fear is {fear_w}; "
        f"affection is {affection_w}; "
        f"suspicion is {suspicion_w}."
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


# ──────────────────────────────────────────────────────────────────────────────
# Character type — structural role in the engine (distinct from story role)
# ──────────────────────────────────────────────────────────────────────────────

class CharacterType(str, Enum):
    """Engine-level classification of every participant in the game.

    This is separate from the story-level `role` string (e.g. "ghost", "ally").
    character_type controls how the engine creates, routes, and tracks each character.
    """
    USER = "user"
    MAIN = "main"
    CANONICAL = "canonical"
    NPC = "npc"


# ──────────────────────────────────────────────────────────────────────────────
# Relationship types — the nature of the connection between two characters
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# RelationshipState — numeric dimensions on a single directed edge
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RelationshipState:
    """Multi-dimensional relationship state (A's perspective toward B)."""
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
        """Map multi-dimensional state to legacy integer score (-5..+5)."""
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


# ──────────────────────────────────────────────────────────────────────────────
# RelationshipEdge — one directed edge representing how from_id feels about to_id
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RelationshipEdge:
    """A directed edge: from_id's perspective toward to_id.

    label        — static authored context, never changes at runtime
                   e.g. "former manager; contract dispute ended badly"
    narrative    — dynamic runtime note, replaced on each update
                   e.g. "IU now believes Steve is hiding something"
    narrative_log — append-only history of all narrative notes this session
    """
    id: str
    from_id: str
    to_id: str
    type: RelationshipType = RelationshipType.OTHER
    state: RelationshipState = field(default_factory=RelationshipState)
    label: str = ""
    narrative: str = ""
    narrative_log: List[str] = field(default_factory=list)

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
            narrative=str(d.get("narrative", "")),
        )


# ──────────────────────────────────────────────────────────────────────────────
# CharacterGraph — the authoritative container of character nodes + edges
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CharacterGraph:
    """Directed graph of character nodes and relationship edges.

    Node storage:
        characters: Dict[str, Character]  — keyed by character.key

    Edge storage:
        edges: Dict[str, RelationshipEdge] — keyed "{from_id}->{to_id}"
        Uniqueness: exactly one edge per ordered (from_id, to_id) pair.

    All query methods return RelationshipEdge or List[RelationshipEdge].
    """
    characters: Dict[str, Any] = field(default_factory=dict)   # key → Character
    edges: Dict[str, RelationshipEdge] = field(default_factory=dict)  # "a->b" → edge

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _edge_key(from_id: str, to_id: str) -> str:
        """Canonical storage key for a directed edge (O(1) lookup)."""
        return f"{from_id}->{to_id}"

    # ── Character node queries ────────────────────────────────────────────────

    def add_character(self, character: "Character") -> None:
        """Add or replace a character node in the graph."""
        self.characters[character.key] = character

    def get_character(self, character_id: str) -> Optional["Character"]:
        """Return a character node by key, or None."""
        return self.characters.get(character_id)

    # ── Edge queries — all return RelationshipEdge or List[RelationshipEdge] ──

    def get_edge(self, from_id: str, to_id: str) -> Optional[RelationshipEdge]:
        """Return the directed edge from from_id to to_id, or None."""
        return self.edges.get(self._edge_key(from_id, to_id))

    def get_edges_from(self, character_id: str) -> List[RelationshipEdge]:
        """All edges where character_id is the source (outgoing)."""
        return [e for e in self.edges.values() if e.from_id == character_id]

    def get_edges_to(self, character_id: str) -> List[RelationshipEdge]:
        """All edges where character_id is the target (incoming)."""
        return [e for e in self.edges.values() if e.to_id == character_id]

    def get_all_relationships(self, character_id: str) -> List[RelationshipEdge]:
        """All edges where character_id appears as either source or target."""
        return [
            e for e in self.edges.values()
            if e.from_id == character_id or e.to_id == character_id
        ]

    def get_room_relationships(self, character_ids: set[str]) -> List[RelationshipEdge]:
        """All edges between any pair of characters within character_ids.

        Use this when entering a location: pass the set of characters present
        (including "player") to retrieve every directed relationship in the room.

        Example — room with player, iu, steve:
            graph.get_room_relationships({"player", "iu", "steve"})
            → [iu→player, iu→steve, steve→player, steve→iu, player→iu, ...]
        """
        ids = set(character_ids)
        return [
            e for e in self.edges.values()
            if e.from_id in ids and e.to_id in ids
        ]

    # ── Edge mutations ────────────────────────────────────────────────────────

    def update_edge(
        self,
        from_id: str,
        to_id: str,
        *,
        trust_delta: float = 0.0,
        fear_delta: float = 0.0,
        affection_delta: float = 0.0,
        suspicion_delta: float = 0.0,
        narrative: str = "",
    ) -> bool:
        """Apply dimensional deltas and an optional narrative note to an existing edge.

        Returns True if the edge was found and updated, False if not found.
        narrative replaces edge.narrative and is appended to narrative_log.
        Only edges that already exist in the graph can be updated.
        """
        edge = self.get_edge(from_id, to_id)
        if edge is None:
            return False
        edge.state.apply_delta(
            trust=trust_delta,
            fear=fear_delta,
            affection=affection_delta,
            suspicion=suspicion_delta,
        )
        if narrative:
            edge.narrative = narrative.strip()
            edge.narrative_log.append(narrative.strip())
        return True

    def apply_rel_delta(self, from_id: str, to_id: str, rel_delta: int) -> None:
        """Backward compat: map legacy rel_delta (-1/0/+1) to affection delta."""
        self.update_edge(from_id, to_id, affection_delta=rel_delta * 0.1)

    # ── Prompt formatting ─────────────────────────────────────────────────────

    def format_for_prompt(
        self,
        speaker_id: str,
        characters: dict | None = None,
        active_characters: set[str] | None = None,
    ) -> str:
        """Build the relationship context block for the system prompt.

        Args:
            speaker_id:        character whose outgoing relationships to show
            characters:        optional external name-lookup dict (falls back to
                               self.characters if omitted)
            active_characters: if provided, only include edges to these character keys

        Returns:
            Formatted multi-line string, or empty string if no relevant edges.
        """
        char_lookup = characters if characters is not None else self.characters

        edges = self.get_edges_from(speaker_id)
        if not edges:
            return ""

        if active_characters is not None:
            edges = [e for e in edges if e.to_id in active_characters]
            if not edges:
                return ""

        # Cap at 6 edges for prompt size
        edges = edges[:6]

        lines = []
        for e in edges:
            target = char_lookup.get(e.to_id)
            name = getattr(target, "name", None) or e.to_id
            if e.to_id == "player":
                name = "The Player"

            label_name = f"{name} ({e.to_id})"
            type_label = e.type.value.lower().replace("_", " ")
            described = describe_relationship_state(e.state)

            line = f"- {label_name} ({type_label}): {described['summary']}"
            line += f"\n  {described['stance']}"
            if e.label:
                line += f"\n  [Context] {e.label}"
            if e.narrative:
                line += f"\n  [Now] {e.narrative}"
            lines.append(line)

        return "\n".join(lines)

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: Dict[str, Any] | None) -> "CharacterGraph":
        """Parse from story JSON relationships section.

        Accepts dict-keyed or list-of-dicts edge format.
        Edges are stored with canonical '{from_id}->{to_id}' keys for O(1) lookup.
        Authored edges with symmetric=true generate an explicit reverse edge so
        both directions are queryable without runtime flag checks.
        """
        if not d:
            return cls()

        raw_edges = d.get("edges") or {}
        if isinstance(raw_edges, list):
            raw_list = raw_edges
        else:
            raw_list = [{"id": eid, **edata} for eid, edata in raw_edges.items()]

        graph = cls()
        for item in raw_list:
            eid = str(item.get("id", f"edge_{len(graph.edges)}"))
            edge = RelationshipEdge.from_dict(eid, item)
            if not edge.from_id or not edge.to_id:
                continue

            key = cls._edge_key(edge.from_id, edge.to_id)
            graph.edges[key] = edge

            # Authored symmetric=true → create explicit reverse edge for O(1) lookup
            if item.get("symmetric"):
                rev_key = cls._edge_key(edge.to_id, edge.from_id)
                if rev_key not in graph.edges:
                    graph.edges[rev_key] = RelationshipEdge(
                        id=f"{eid}_rev",
                        from_id=edge.to_id,
                        to_id=edge.from_id,
                        type=edge.type,
                        state=RelationshipState(
                            trust=edge.state.trust,
                            fear=edge.state.fear,
                            affection=edge.state.affection,
                            suspicion=edge.state.suspicion,
                        ),
                        label=edge.label,
                        narrative=edge.narrative,
                    )

        return graph

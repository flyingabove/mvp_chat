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
  state        — five numeric dimensions (trust, fear, affection, suspicion, jealousy)
  label        — static authored context, never changes ("former manager, dispute")
  narrative    — dynamic runtime note, replaced on each update by the LLM
  narrative_log — append-only session history of all narrative notes

  Relationship history (engine-tracked via process_first_meetings):
    met_at        — game minute of first physical co-location (0 = pre-game)
    last_met_at   — most recent encounter minute
    meeting_count — distinct encounter count this session

  Relationship history (LLM-extracted via TurnExtractor):
    prior_relationship — ever been in a romantic relationship
    prior_intimacy     — ever been sexually intimate
    in_relationship    — currently in a relationship

PLAYER AS CHARACTER
────────────────────
The player (key="player", character_type=USER) is a full first-class node.
player→NPC edges are created by process_first_meetings() and updated each turn
by RelationshipStateUpdate objects extracted from the player's message (small
±0.10 deltas on trust/fear/affection/suspicion/jealousy).
See turn_extractor.py for RelationshipStateUpdate; see prompt_builder.py for
how the player's attitude is surfaced in the NPC's prompt context.

RELATIONSHIP TRAIT DIMENSIONS
──────────────────────────────
  trust      -1..1   How much A trusts B. Negative = active distrust.
  fear        0..1   How afraid A is of B. High fear + low trust = defensive/hostile.
  affection  -1..1   Emotional warmth. Negative = resentment/hatred.
  suspicion   0..1   How much A suspects B of wrongdoing.
  jealousy    0..1   How jealous A is toward B. 5 discrete levels: 0, 0.25, 0.5, 0.75, 1.0.
                     Increments are bounded by REL_TRAIT_DELTA_MIN and REL_TRAIT_DELTA_MAX
                     in backend/app/config/settings.py.

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

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from backend.app.engine.social_traits import EvolvingTrait

if TYPE_CHECKING:
    from backend.app.engine.state import Character, GameState


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

# Jealousy has 5 discrete levels at 0.25 intervals (0..1 range).
# See REL_TRAIT_DELTA_MIN / REL_TRAIT_DELTA_MAX in settings.py for increment bounds.
_JEALOUSY_WORDS: dict[float, str] = {
    0.00: "secure",
    0.25: "mild",
    0.50: "moderate",
    0.75: "strong",
    1.00: "consuming",
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


def _round_quarter(value: float) -> float:
    """Snap a 0..1 value to the nearest 0.25 step (0.0, 0.25, 0.5, 0.75, 1.0)."""
    v = max(0.0, min(1.0, float(value)))
    steps = [0.0, 0.25, 0.5, 0.75, 1.0]
    return min(steps, key=lambda s: abs(v - s))


def _word_from_jealousy(value: float) -> str:
    """Return the deterministic word for a jealousy value (0..1, 5 discrete levels)."""
    return _JEALOUSY_WORDS[_round_quarter(value)]


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
    jealousy_n = _round_quarter(state.jealousy)

    trust_w = _word_from_scale(_TRUST_WORDS, trust_n)
    fear_w = _word_from_scale(_FEAR_WORDS, fear_n)
    affection_w = _word_from_scale(_AFFECTION_WORDS, affection_n)
    suspicion_w = _word_from_scale(_SUSPICION_WORDS, suspicion_n)
    jealousy_w = _word_from_jealousy(jealousy_n)

    summary = (
        f"Trust is {trust_w}; "
        f"fear is {fear_w}; "
        f"affection is {affection_w}; "
        f"suspicion is {suspicion_w}; "
        f"jealousy is {jealousy_w}."
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
        "jealousy_normalized": jealousy_n,
        "trust_word": trust_w,
        "fear_word": fear_w,
        "affection_word": affection_w,
        "suspicion_word": suspicion_w,
        "jealousy_word": jealousy_w,
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
    """Multi-dimensional relationship state (A's perspective toward B).

    trust      -1..1   How much A trusts B. Negative = active distrust.
    fear        0..1   How afraid A is of B.
    affection  -1..1   Emotional warmth. Negative = resentment/hatred.
    suspicion   0..1   How much A suspects B of wrongdoing.
    jealousy    0..1   How jealous A is toward B. 5 discrete word levels at 0.25 intervals.
                       Per-turn increments bounded by REL_TRAIT_DELTA_MIN/MAX in settings.py.
    """
    trust: float = 0.0       # -1..1  How much A trusts B
    fear: float = 0.0        # 0..1   How afraid A is of B
    affection: float = 0.0   # -1..1  Emotional warmth (negative = resentment)
    suspicion: float = 0.0   # 0..1   How much A suspects B of wrongdoing
    jealousy: float = 0.0    # 0..1   How jealous A is toward B (5 discrete levels)

    def __post_init__(self) -> None:
        self._clamp()

    def _clamp(self) -> None:
        self.trust = max(-1.0, min(1.0, float(self.trust)))
        self.fear = max(0.0, min(1.0, float(self.fear)))
        self.affection = max(-1.0, min(1.0, float(self.affection)))
        self.suspicion = max(0.0, min(1.0, float(self.suspicion)))
        self.jealousy = max(0.0, min(1.0, float(self.jealousy)))

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
            jealousy=float(d.get("jealousy", 0.0)),
        )


# ──────────────────────────────────────────────────────────────────────────────
# RelationshipEdge — one directed edge representing how from_id feels about to_id
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RelationshipEdge:
    """A directed edge: from_id's perspective toward to_id.

    label         — static authored context, never changes at runtime
                    e.g. "former manager; contract dispute ended badly"
    narrative     — dynamic runtime note, replaced on each update
                    e.g. "IU now believes Steve is hiding something"
    narrative_log — append-only history of all narrative notes this session

    Relationship history (engine-tracked):
      met_at       — game minute of first physical co-location this session.
                     None = haven't met yet. 0 = met before game started.
      last_met_at  — game minute of most recent co-location encounter.
                     Updated each time process_first_meetings fires as a new encounter.
      meeting_count — distinct encounter count this session. Pre-seeded from JSON.

    Relationship history (LLM-extracted via TurnExtractor):
      prior_relationship — ever been in a romantic relationship
      prior_intimacy     — ever been sexually intimate
      in_relationship    — currently in a relationship
    """
    id: str
    from_id: str
    to_id: str
    type: RelationshipType = RelationshipType.OTHER
    state: RelationshipState = field(default_factory=RelationshipState)
    label: str = ""
    narrative: str = ""
    narrative_log: List[str] = field(default_factory=list)
    met_at: Optional[int] = None        # None = not yet physically met this session
    last_met_at: Optional[int] = None   # most recent encounter minute
    meeting_count: int = 0              # distinct encounters this session
    prior_relationship: bool = False    # ever been in a romantic relationship (LLM-extracted)
    prior_intimacy: bool = False        # ever been sexually intimate (LLM-extracted)
    in_relationship: bool = False       # currently in a relationship (LLM-extracted)
    # Phase 3 "Social life": from_id's evolving disposition toward to_id
    # specifically (e.g. "in love with", "growing suspicious of",
    # "aggressive toward"), distinct from the numeric RelationshipState axes
    # above - a disposition is a qualitative narrative label with a full
    # auditable change history, not a point on a fixed numeric scale. None
    # until the extractor (or story authoring) establishes one; always
    # renders as nothing when absent (see format_for_prompt).
    disposition: Optional[EvolvingTrait] = None

    @classmethod
    def from_dict(cls, edge_id: str, d: Dict[str, Any] | None) -> "RelationshipEdge":
        d = d or {}
        type_raw = str(d.get("type", "OTHER")).upper()
        try:
            rel_type = RelationshipType(type_raw)
        except ValueError:
            rel_type = RelationshipType.OTHER
        # met_before_game=true → characters knew each other before the game started
        met_at: Optional[int] = 0 if d.get("met_before_game") else None
        last_met_at_raw = d.get("last_met_at")
        last_met_at: Optional[int] = int(last_met_at_raw) if last_met_at_raw is not None else None
        from_id = str(d.get("from_id") or d.get("from", ""))
        # Optional authoring surface: a story may seed a starting disposition
        # as a plain string (e.g. "already smitten with her roommate").
        # Serialized EvolvingTrait dicts (session restore) are handled by
        # _restore_character_graph in prompt_engine.py, not here - from_dict
        # is the author-time story-JSON parsing path only.
        raw_disposition = d.get("disposition")
        disposition: Optional[EvolvingTrait] = None
        if isinstance(raw_disposition, str) and raw_disposition.strip():
            disposition = EvolvingTrait(kind="disposition", subject_id=from_id, target_id=str(d.get("to_id") or d.get("to", "")))
            disposition.set_initial(raw_disposition.strip())
        return cls(
            id=edge_id,
            from_id=from_id,
            to_id=str(d.get("to_id") or d.get("to", "")),
            type=rel_type,
            state=RelationshipState.from_dict(d.get("state")),
            label=str(d.get("label", "")),
            narrative=str(d.get("narrative", "")),
            met_at=met_at,
            last_met_at=last_met_at,
            meeting_count=int(d.get("meeting_count", 0)),
            prior_relationship=bool(d.get("prior_relationship", False)),
            prior_intimacy=bool(d.get("prior_intimacy", False)),
            in_relationship=bool(d.get("in_relationship", False)),
            disposition=disposition,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Prejudice initialization — deterministic first-meeting trait calculation
# ──────────────────────────────────────────────────────────────────────────────

# Role keyword → (trust_delta, fear_delta, suspicion_delta, affection_delta)
_ROLE_PRIORS: list[tuple[list[str], tuple[float, float, float, float]]] = [
    (["suspect", "criminal", "killer", "murderer", "villain"],  (-0.15, +0.05, +0.25, -0.10)),
    (["antagonist", "enemy", "rival"],                          (-0.10, +0.05, +0.10, -0.05)),
    (["ally", "partner", "friend", "helper"],                   (+0.10,  0.00, -0.05, +0.10)),
    (["authority", "detective", "inspector", "officer", "doctor"],
                                                                (+0.05, +0.05,  0.00,  0.00)),
    (["victim", "witness"],                                     ( 0.00,  0.00, -0.05, +0.05)),
]

# Tag keyword → (trust_delta, fear_delta, suspicion_delta, affection_delta)
_TAG_PRIORS: list[tuple[list[str], tuple[float, float, float, float]]] = [
    (["dangerous", "violent", "criminal", "threatening"],       ( 0.00, +0.05, +0.10,  0.00)),
    (["friendly", "trustworthy", "kind", "loyal"],              (+0.05,  0.00,  0.00, +0.05)),
]

_NEGATIVE_FACT_KEYWORDS = re.compile(
    r"\b(killed|murdered|stole|lied|deceived|threatened|attacked|violent|crime|assault)\b",
    re.IGNORECASE,
)
_POSITIVE_FACT_KEYWORDS = re.compile(
    r"\b(helped|saved|honest|trustworthy|kind|loyal|protected)\b",
    re.IGNORECASE,
)


def _compute_prejudice_state(
    a_char: "Character",
    b_char: "Character",
    state: "GameState",
) -> "tuple[RelationshipState, RelationshipType]":
    """Compute A's initial RelationshipState toward B using deterministic prejudice rules.

    Called when A and B physically meet for the first time and no authored edge exists.
    Signals used (all deterministic, no LLM):
      A. b_char.role keyword match → role-based prior
      B. b_char.is_suspect flag → suspicion/trust adjustment
      C. b_char.tags keyword match → tag-based prior
      D. Canonical facts A knows about B → negative/positive keyword scan

    Returns (RelationshipState, inferred RelationshipType).
    All deltas are clamped via RelationshipState._clamp() at end.
    """
    trust = 0.0
    fear = 0.0
    suspicion = 0.0
    affection = 0.0

    # A. Role-based prior
    b_role = (getattr(b_char, "role", "") or "").lower()
    for keywords, (t, f, s, aff) in _ROLE_PRIORS:
        if any(kw in b_role for kw in keywords):
            trust += t; fear += f; suspicion += s; affection += aff
            break  # only apply the first matching group

    # B. is_suspect flag
    if getattr(b_char, "is_suspect", False):
        suspicion += 0.15
        trust -= 0.10

    # C. Tag-based prior
    b_tags = [t.lower() for t in (getattr(b_char, "tags", None) or [])]
    for keywords, (t, f, s, aff) in _TAG_PRIORS:
        if any(kw in tag for kw in keywords for tag in b_tags):
            trust += t; fear += f; suspicion += s; affection += aff

    # D. Canonical facts that A knows about B
    a_key = getattr(a_char, "key", "")
    b_key = getattr(b_char, "key", "")
    b_name = (getattr(b_char, "name", "") or "").lower()
    canonical_facts = getattr(state, "canonical_facts", None) or []

    neg_hits = 0
    pos_hits = 0
    for chunk in canonical_facts:
        # Check if A knows this fact
        known_by = getattr(chunk, "known_by", None) or []
        if a_key not in known_by and "all_characters" not in known_by:
            continue
        # Check if fact is about B
        fact_text = str(getattr(chunk, "text", "") or getattr(chunk, "content", "") or "").lower()
        fact_subject = str(getattr(chunk, "subject", "") or "").lower()
        if b_key not in fact_text and b_name not in fact_text and b_key not in fact_subject:
            continue
        # Keyword scan
        if neg_hits < 2 and _NEGATIVE_FACT_KEYWORDS.search(fact_text):
            trust -= 0.10
            suspicion += 0.10
            neg_hits += 1
        if pos_hits < 2 and _POSITIVE_FACT_KEYWORDS.search(fact_text):
            trust += 0.10
            affection += 0.05
            pos_hits += 1

    rs = RelationshipState(trust=trust, fear=fear, affection=affection, suspicion=suspicion)
    # _clamp() is called in __post_init__ already, but apply it explicitly after assignment
    rs._clamp()

    # E. Infer RelationshipType from computed state
    if rs.suspicion >= 0.30:
        rel_type = RelationshipType.SUSPECT
    elif rs.trust <= -0.20 and rs.affection <= -0.10:
        rel_type = RelationshipType.ENEMY
    elif rs.affection >= 0.20 and rs.trust >= 0.10:
        rel_type = RelationshipType.FRIEND
    elif rs.fear >= 0.25:
        rel_type = RelationshipType.WITNESS
    else:
        rel_type = RelationshipType.OTHER

    return rs, rel_type


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
        jealousy_delta: float = 0.0,
        narrative: str = "",
    ) -> bool:
        """Apply dimensional deltas and an optional narrative note to an existing edge.

        Returns True if the edge was found and updated, False if not found.
        narrative replaces edge.narrative and is appended to narrative_log.
        Only edges that already exist in the graph can be updated.
        Delta values should stay within [REL_TRAIT_DELTA_MIN, REL_TRAIT_DELTA_MAX]
        per interaction (or 0 if nothing changed) — see settings.py.
        """
        edge = self.get_edge(from_id, to_id)
        if edge is None:
            return False
        edge.state.apply_delta(
            trust=trust_delta,
            fear=fear_delta,
            affection=affection_delta,
            suspicion=suspicion_delta,
            jealousy=jealousy_delta,
        )
        if narrative:
            edge.narrative = narrative.strip()
            edge.narrative_log.append(narrative.strip())
        return True

    def apply_rel_delta(self, from_id: str, to_id: str, rel_delta: int) -> None:
        """Backward compat: map legacy rel_delta (-1/0/+1) to affection delta."""
        self.update_edge(from_id, to_id, affection_delta=rel_delta * 0.1)

    def update_edge_history(
        self,
        from_id: str,
        to_id: str,
        *,
        prior_relationship: Optional[bool] = None,
        prior_intimacy: Optional[bool] = None,
        in_relationship: Optional[bool] = None,
    ) -> bool:
        """Apply LLM-extracted relationship history fields to an existing edge.

        Only fields passed as non-None are updated. Returns True if edge found.
        Called by prompt_engine after processing TurnExtractor relationship_history_updates.
        """
        edge = self.get_edge(from_id, to_id)
        if edge is None:
            return False
        if prior_relationship is not None:
            edge.prior_relationship = prior_relationship
        if prior_intimacy is not None:
            edge.prior_intimacy = prior_intimacy
        if in_relationship is not None:
            edge.in_relationship = in_relationship
        return True

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
            if e.disposition is not None and e.disposition.current:
                line += f"\n  [Disposition] {e.disposition.current}"
            lines.append(line)

        return "\n".join(lines)

    # ── First-meeting detection + prejudice initialization ─────────────────────

    def process_first_meetings(
        self,
        room_ids: "Set[str]",
        state: "GameState",
        current_minute: int,
        is_new_encounter: bool = False,
    ) -> None:
        """Detect first physical meetings and initialize prejudice on new edges.

        Called every turn with the current room set so NPC walk-ins are captured.
        For each ordered pair (A, B) in the room:
          - If the A→B edge exists and met_at is None: first meeting — set met_at,
            last_met_at, and meeting_count = 1.
          - If the A→B edge exists and met_at is set: if is_new_encounter, update
            last_met_at and increment meeting_count.
          - If the A→B edge does not exist: create it with prejudice-initialized
            values computed from available identity and epistemic signals.

        is_new_encounter=True should be passed when the player just entered a new
        location (location_changed) or an NPC just walked into the room. Set False
        for turns where the room composition hasn't changed.

        Idempotent for first meetings: once met_at is set it is never reset.
        """
        ids = sorted(room_ids)  # deterministic ordering
        for a_id in ids:
            for b_id in ids:
                if a_id == b_id:
                    continue
                edge = self.get_edge(a_id, b_id)
                if edge is not None:
                    if edge.met_at is None:
                        # First physical meeting this session
                        edge.met_at = current_minute
                        edge.last_met_at = current_minute
                        edge.meeting_count = 1
                    elif is_new_encounter:
                        # Re-entering same location or NPC walked in
                        edge.last_met_at = current_minute
                        edge.meeting_count += 1
                else:
                    # No authored edge — create one with prejudice-initialized values
                    a_char = self.characters.get(a_id)
                    b_char = self.characters.get(b_id)
                    if a_char is None or b_char is None:
                        continue
                    init_state, inferred_type = _compute_prejudice_state(a_char, b_char, state)
                    new_edge = RelationshipEdge(
                        id=self._edge_key(a_id, b_id),
                        from_id=a_id,
                        to_id=b_id,
                        type=inferred_type,
                        state=init_state,
                        met_at=current_minute,
                        last_met_at=current_minute,
                        meeting_count=1,
                    )
                    self.edges[self._edge_key(a_id, b_id)] = new_edge

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
                            jealousy=edge.state.jealousy,
                        ),
                        label=edge.label,
                        narrative=edge.narrative,
                        met_at=edge.met_at,
                        last_met_at=edge.last_met_at,
                        meeting_count=edge.meeting_count,
                        prior_relationship=edge.prior_relationship,
                        prior_intimacy=edge.prior_intimacy,
                        in_relationship=edge.in_relationship,
                    )

        return graph

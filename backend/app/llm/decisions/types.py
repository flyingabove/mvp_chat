# backend/app/llm/decisions/types.py
"""Provider-independent decision contract.

Exact contract from documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §3.
Pure data — no I/O. These types are what makes a Decision answerable by
either Jev or the legacy generative extractor without either side knowing
about the other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Mapping, Sequence


class Criticality(Enum):
    """Decides fallback granularity when a Jev answer is unusable.

    See JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §5 for the full rationale:
    every DEGRADABLE assignment must be justified by an EXISTING "omit if
    ambiguous/neutral" rule already present in the legacy extractor prompt,
    so nothing becomes newly optional because of this design.
    """
    CRITICAL = "critical"      # an engine invariant depends on it -> full
                               # legacy re-extraction for the whole turn
    DEGRADABLE = "degradable"  # absence is already a valid state today ->
                               # leave the field at its dataclass default


class Provider(Enum):
    JEV = "jev"
    LEGACY_LLM = "legacy_llm"
    DEFAULT = "default"        # nothing answered; dataclass default used


class FallbackReason(Enum):
    NONE = "none"
    FLAG_DISABLED = "flag_disabled"        # task not enabled -> never tried Jev
    CIRCUIT_OPEN = "circuit_open"          # breaker open -> skipped Jev
    SHADOW_MODE = "shadow_mode"            # Jev ran, answer deliberately unused
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    MALFORMED_RESPONSE = "malformed_response"
    MISSING_ANSWER = "missing_answer"      # question id absent from answers
    INVALID_OPTION = "invalid_option"      # choice not in `allowed`
    BELOW_THRESHOLD = "below_threshold"    # confidence/probability too low


@dataclass(frozen=True)
class Decision:
    """One bounded question. Pure data — no I/O, no provider knowledge."""
    id: str                                   # stable; used as the Jev question key
    task: str                                 # rollout flag group, e.g. "movement"
    kind: Literal["choice", "score", "noul"]
    instructions: str
    criteria: Mapping[str, str] | Sequence[str]
    criticality: Criticality

    # --- validation, applied to whatever provider answered ---
    allowed: frozenset[str] | None = None     # choice: valid option ids
    none_option: str | None = None            # choice: the "no answer" option
    min_confidence: float | None = None       # choice/score: reject below this
    true_threshold: float | None = None       # noul: p >= this means True

    # --- how the legacy LLM answer maps onto this decision ---
    # `legacy_path`: for a SCALAR field reachable by walking nested dicts,
    # e.g. ("movement", "intent") -> legacy_raw["movement"]["intent"].
    # Sufficient for abilities 1/2/5 (step 5) where the legacy JSON's shape
    # already matches one decision one field.
    legacy_path: tuple[str, ...] = ()

    # `legacy_resolver`: for anything legacy_path can't express - steps 6+
    # abilities are fan-outs (one Decision per chunk/resident/pair) over a
    # legacy field that is a LIST of objects (knowledge_updates: search for
    # a matching chunk_id) or a single object naming AT MOST ONE match
    # (departure_signal: check character_id, default to NONE for every
    # other resident). Both patterns need real search/matching logic, not a
    # static path - a small deterministic closure is simpler and more
    # honest than inventing a path-matching mini-language for two shapes.
    # Still "pure data" in the sense that matters here: zero I/O, built
    # fresh per turn in decision_registry.py's factory functions (which
    # already build Decision objects dynamically, e.g.
    # movement_destination_decision() takes world_locations per call) - not
    # a violation of the "no I/O" purity rule, which is about network/
    # filesystem access, not about being JSON-serializable.
    # Takes the full legacy_raw dict (or None), returns the raw value this
    # decision's `kind` expects (str for choice, float for score, bool for
    # noul) or None if not found. When set, `legacy_resolver` takes
    # precedence over `legacy_path` for the same Decision.
    legacy_resolver: Callable[[dict[str, Any] | None], Any] | None = None


@dataclass(frozen=True)
class DecisionBatch:
    """Decisions sharing one `state` blob, sent as ONE Jev request."""
    name: str                                 # "current_message" | "previous_reply" | "ripe_window"
    state: str
    decisions: tuple[Decision, ...]


@dataclass(frozen=True)
class DecisionAnswer:
    """Provider-independent answer for one Decision."""
    decision_id: str
    provider: Provider
    # exactly one of these is populated per `kind`
    choice: str | None = None
    score: float | None = None
    probability: float | None = None
    # always populated when the provider supplies it
    confidence: float | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)
    fallback_reason: FallbackReason = FallbackReason.NONE

    @property
    def usable(self) -> bool:
        return self.fallback_reason is FallbackReason.NONE


@dataclass(frozen=True)
class DecisionOutcome:
    """Everything one turn's resolution produced. Consumed by the assembler."""
    answers: Mapping[str, DecisionAnswer]     # decision_id -> answer
    legacy_raw: dict[str, Any] | None         # legacy JSON, if the legacy path ran
    provider_used: Provider                   # dominant provider for this turn
    jev_latency_ms: float | None
    legacy_latency_ms: float | None
    jev_usage: Mapping[str, int] | None       # input/output tokens
    fallback_reasons: Mapping[str, FallbackReason]
    shadow_disagreements: Mapping[str, tuple[Any, Any]]  # id -> (jev, legacy)

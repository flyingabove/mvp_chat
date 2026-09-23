# backend/app/llm/protocols.py
"""Shared provider protocols.

Defined once here per JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §5 /
PHASE_2_BACKEND_RESTRUCTURE_DESIGN_2026_09_22.md §5: both the Jev design and
the Phase 2 backend restructure depend on this exact seam. Jev's
DecisionResolver (backend/app/llm/decisions/resolver.py, step 3+) IS a
DecisionProvider implementation — TurnExtractor depends only on this
protocol, never on Jev directly, so Jev can be swapped, mocked, or disabled
without TurnExtractor's code changing.

Step 2 note: these protocols are not wired to any call site yet. That is
step 3 of the Jev implementation order (JEV_PROVIDER_ARCHITECTURE_2026_09_22.md
§12) — refactoring TurnExtractor into a batch builder / resolver / assembler.
LegacyExtractionRequest's exact field set may be refined then, once the
batch-builder code that constructs it is actually written; the shape below
reflects every input TurnExtractor.extract() takes today
(backend/app/engine/extractors/turn_extractor.py), so nothing is invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from backend.app.llm.decisions.types import DecisionBatch, DecisionOutcome


@dataclass(frozen=True)
class LegacyExtractionRequest:
    """Everything the existing one-shot generative extractor call needs to
    run standalone. Mirrors TurnExtractor.extract()'s current keyword
    arguments exactly (turn_extractor.py) so the legacy path used as
    CRITICAL-decision fallback needs no new plumbing at the call site.
    """
    user_msg: str
    world_locations: Mapping[str, str]
    character_key_to_name: Mapping[str, str]
    previous_turn_user_msg: str = ""
    previous_turn_assistant_reply: str = ""
    previous_turn_candidate_chunks: Sequence[Mapping[str, str]] = ()
    conversation_log: Sequence[Mapping[str, str]] = ()
    behavior_window: Mapping[str, Any] | None = None
    # The actual legacy call, injected so DecisionResolver never imports
    # TurnExtractor (would create an engine <-> llm import cycle). Returns
    # the legacy call's raw parsed JSON dict (pre-TurnExtraction-assembly),
    # so resolve() can read whichever fields a CRITICAL decision needs via
    # Decision.legacy_path without depending on TurnExtraction's shape.
    invoke: Callable[[], Awaitable[dict[str, Any] | None]] | None = None


class DecisionProvider(Protocol):
    """Resolves bounded decisions. Jev's DecisionResolver IS a
    DecisionProvider — this protocol is what makes it swappable/mockable
    without TurnExtractor knowing Jev exists."""

    async def resolve(
        self,
        batches: Sequence[DecisionBatch],
        legacy_request: LegacyExtractionRequest,
    ) -> DecisionOutcome: ...


@dataclass(frozen=True)
class TextResult:
    """Provider-independent generated-text result."""
    text: str
    model: str
    usage: Mapping[str, int] = field(default_factory=dict)


class TextProvider(Protocol):
    """Generates prose. The storyteller call and the Chinese translation
    call both become TextProvider implementations — same interface, so
    Phase 3's 'lifespan-managed HTTP clients' item (persistent clients) is
    implemented ONCE here, not per call site."""

    async def generate(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> TextResult: ...

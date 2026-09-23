# backend/app/llm/usage.py
"""Per-turn token/cost accounting, attributed by provider and task.

Per JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §10: "Extend UsageLedger to
attribute tokens per provider, so 'cost per successfully committed turn'
(the Phase 0B metric) splits into storyteller / Jev / legacy-extraction /
memory." Designed to be merged into the existing turn_stage_ledger JSONL
line (backend/app/utils/stage_timer.py) via `as_ledger_entries()`, not as a
separate log stream — one line per turn stays the single source of truth
for "what did this turn cost."

Pricing figures are the exact ones already used in
documentation/JEV_EXTRACTOR_REDESIGN_2026_09_22.md §8's cost model — kept
here as the one place they're defined, not duplicated per call site.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# $ per million tokens. Source: JEV_EXTRACTOR_REDESIGN_2026_09_22.md §8.
# NOT read from any provider response — these are known list prices, used
# only to compute an ESTIMATED cost figure for the ledger. If a provider
# ever reports real cost directly, prefer that instead of estimating.
PRICING_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    "jev": {"input": 0.042, "output": 0.0},
    "gpt-4o-mini": {"input": 0.15, "input_cached": 0.075, "output": 0.60},
}


def estimate_cost_usd(model: str, usage: dict[str, int]) -> float | None:
    """Returns None (not an error) when the model isn't in the pricing
    table — an unknown model must never silently cost $0.00 in a report,
    which would look like a real, free call."""
    # Jev resolves to versioned names like "jev-1.13.0"; match by prefix
    # rather than requiring an exact, ever-changing version string.
    key = None
    if model.startswith("jev"):
        key = "jev"
    elif model in PRICING_PER_MILLION_TOKENS:
        key = model
    if key is None:
        return None

    prices = PRICING_PER_MILLION_TOKENS[key]
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    cached_tokens = int(usage.get("cached_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    uncached_input = max(0, input_tokens - cached_tokens)

    cost = (uncached_input / 1_000_000.0) * prices["input"]
    cost += (cached_tokens / 1_000_000.0) * prices.get("input_cached", prices["input"])
    cost += (output_tokens / 1_000_000.0) * prices["output"]
    return cost


@dataclass
class UsageEntry:
    provider: str          # "jev" | "legacy_llm" | "storyteller" | ...
    task: str              # "movement" | "storyteller" | "memory_extraction" | ...
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None


class UsageLedger:
    """Accumulates every provider call made during one turn. One instance
    per turn — construct fresh, discard after emitting, matching
    StageTimer's own per-turn lifecycle (backend/app/utils/stage_timer.py)."""

    def __init__(self) -> None:
        self._entries: list[UsageEntry] = []

    def record(self, *, provider: str, task: str, model: str, usage: dict[str, int]) -> None:
        self._entries.append(UsageEntry(
            provider=provider, task=task, model=model, usage=dict(usage),
            cost_usd=estimate_cost_usd(model, usage),
        ))

    def entries(self) -> list[UsageEntry]:
        return list(self._entries)

    def total_cost_usd(self) -> float | None:
        """None if ANY entry has an unpriced model — a partial total would
        misreport the turn as cheaper than it was. Callers that want a
        partial figure can sum entries() themselves and note the gap."""
        costs = [e.cost_usd for e in self._entries]
        if any(c is None for c in costs):
            return None
        return sum(c for c in costs if c is not None)

    def as_ledger_entries(self) -> list[dict]:
        """Flat, JSON-serializable form for merging into turn_stage_ledger."""
        return [
            {
                "provider": e.provider, "task": e.task, "model": e.model,
                "usage": e.usage, "cost_usd": e.cost_usd,
            }
            for e in self._entries
        ]

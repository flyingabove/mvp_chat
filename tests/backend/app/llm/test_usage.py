"""Tests for UsageLedger and estimate_cost_usd (backend/app/llm/usage.py)."""
from backend.app.llm.usage import PRICING_PER_MILLION_TOKENS, UsageLedger, estimate_cost_usd


def test_estimate_cost_jev_input_only_output_free():
    """Verified pricing from JEV_EXTRACTOR_REDESIGN_2026_09_22.md §8:
    $0.042/M input, output free."""
    cost = estimate_cost_usd("jev-1.13.0", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert cost == 0.042  # output contributes $0


def test_estimate_cost_matches_by_jev_prefix_not_exact_version_string():
    """jev-latest, jev-1.13.0, a future jev-2.0.0 - all must price the same
    way without needing this table updated every time TypeSafe ships a
    version. The resolved model string always starts with 'jev'."""
    for model in ("jev-latest", "jev-1.13.0", "jev-2.0.0-preview"):
        cost = estimate_cost_usd(model, {"input_tokens": 1_000_000, "output_tokens": 0})
        assert cost == 0.042, f"failed for {model}"


def test_estimate_cost_gpt4o_mini_separates_cached_and_uncached_input():
    """Verified pricing: $0.15/M uncached, $0.075/M cached, $0.60/M output.
    This distinction is the whole point of the Phase 3 prompt-caching
    row - a ledger that can't tell cached from uncached tokens can't
    measure whether that optimization worked."""
    cost = estimate_cost_usd("gpt-4o-mini", {
        "input_tokens": 1_000_000, "cached_tokens": 400_000, "output_tokens": 1_000_000,
    })
    # 600k uncached @ 0.15 + 400k cached @ 0.075 + 1M output @ 0.60
    expected = (600_000 / 1e6) * 0.15 + (400_000 / 1e6) * 0.075 + (1_000_000 / 1e6) * 0.60
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_unknown_model_returns_none_not_zero():
    """An unknown model must never silently report $0.00 - that would look
    like a real free call in a report, not a gap in the pricing table."""
    assert estimate_cost_usd("some-future-provider-model", {"input_tokens": 1000}) is None


def test_estimate_cost_accepts_openai_style_field_names_too():
    """Some responses use prompt_tokens/completion_tokens (OpenAI's own
    field names) rather than input_tokens/output_tokens (Jev's) - the
    estimator must handle both without the caller normalizing first."""
    cost = estimate_cost_usd("gpt-4o-mini", {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    assert cost == 0.15


def test_ledger_records_multiple_providers_in_one_turn():
    ledger = UsageLedger()
    ledger.record(provider="jev", task="movement", model="jev-1.13.0",
                   usage={"input_tokens": 1200, "output_tokens": 0})
    ledger.record(provider="legacy_llm", task="storyteller", model="gpt-4o-mini",
                   usage={"input_tokens": 4800, "output_tokens": 240})
    entries = ledger.entries()
    assert len(entries) == 2
    assert {e.provider for e in entries} == {"jev", "legacy_llm"}


def test_ledger_total_cost_sums_all_priced_entries():
    ledger = UsageLedger()
    ledger.record(provider="jev", task="movement", model="jev-1.13.0", usage={"input_tokens": 1_000_000})
    ledger.record(provider="jev", task="prev_scene", model="jev-1.13.0", usage={"input_tokens": 1_000_000})
    total = ledger.total_cost_usd()
    assert total is not None
    assert abs(total - 0.084) < 1e-9  # 2 x $0.042


def test_ledger_total_cost_is_none_if_any_entry_unpriced():
    """A partial total that silently omits an unpriced call would
    understate real spend - the whole point of estimate_cost_usd returning
    None on an unknown model must propagate to the ledger total, not get
    swallowed as a 0."""
    ledger = UsageLedger()
    ledger.record(provider="jev", task="movement", model="jev-1.13.0", usage={"input_tokens": 1000})
    ledger.record(provider="mystery", task="x", model="unknown-model-xyz", usage={"input_tokens": 1000})
    assert ledger.total_cost_usd() is None


def test_ledger_as_ledger_entries_is_json_serializable_shape():
    import json
    ledger = UsageLedger()
    ledger.record(provider="jev", task="movement", model="jev-1.13.0", usage={"input_tokens": 100})
    entries = ledger.as_ledger_entries()
    json.dumps(entries)  # must not raise
    assert entries[0]["provider"] == "jev"
    assert entries[0]["cost_usd"] is not None


def test_ledger_empty_by_default():
    ledger = UsageLedger()
    assert ledger.entries() == []
    assert ledger.total_cost_usd() == 0  # sum of nothing is 0, not None (no entries to be unpriced)


def test_pricing_table_has_jev_and_gpt4o_mini():
    """Locks the two models this design currently needs priced; a future
    model addition should extend this table, not replace it silently."""
    assert "jev" in PRICING_PER_MILLION_TOKENS
    assert "gpt-4o-mini" in PRICING_PER_MILLION_TOKENS
    assert PRICING_PER_MILLION_TOKENS["jev"]["output"] == 0.0

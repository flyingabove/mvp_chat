import pytest

from backend.app.config.epistemic_flags import (
    set_epistemic_flags,
)
from backend.app.engine import prompt_builder
from backend.app.integration_playback.scenarios.scenario_epistemic_layer_switch import EpistemicLayerScenario


@pytest.fixture(autouse=True)
def fake_retrieval(monkeypatch):
    """Stub the memory formatter so the test isolates epistemic layer logic."""
    def _fake_memory_block(chunks, story_id):
        return "RETRIEVAL_BLOCK_IS_DETERMINISTIC"

    monkeypatch.setattr(prompt_builder, "_format_memory_block", _fake_memory_block)
    # Update local binding so calls in this module use the stub.
    globals()["_format_memory_block"] = _fake_memory_block
    yield


@pytest.mark.integration
@pytest.mark.parametrize(
    "flags,should_pass",
    [
        ({"master": False}, False),
        ({"truth": False}, False),
        ({"belief": False}, False),
        ({"narrative": False}, False),
        ({"retrieval": False}, False),
        ({}, True),
    ],
)
def test_epistemic_layer_toggles(flags, should_pass):
    with set_epistemic_flags(**flags):
        if should_pass:
            EpistemicLayerScenario.run_as_test()
        else:
            with pytest.raises(AssertionError):
                EpistemicLayerScenario.run_as_test()

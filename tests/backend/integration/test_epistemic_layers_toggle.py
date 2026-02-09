import pytest

from backend.app.config.epistemic_flags import (
    belief_enabled,
    retrieval_enabled,
    narrative_enabled,
    truth_enabled,
    set_epistemic_flags,
)
from backend.app.engine import prompt_builder
from backend.app.engine.epistemic_state import EpistemicClaim, EpistemicFact
from backend.app.engine.state import init_state
from backend.app.integration_playback.scenario import IntegrationScenario, step


@pytest.fixture(autouse=True)
def fake_retrieval(monkeypatch):
    """Stub the memory formatter so the test isolates epistemic layer logic."""
    def _fake_memory_block(chunks, story_id):
        return "RETRIEVAL_BLOCK_IS_DETERMINISTIC"

    monkeypatch.setattr(prompt_builder, "_format_memory_block", _fake_memory_block)
    # Update local binding so calls in this module use the stub.
    globals()["_format_memory_block"] = _fake_memory_block
    yield


class EpistemicLayerScenario(IntegrationScenario):
    scenario_id = "epistemic_layer_switch_validation"
    title = "Epistemic layer toggles must be on"
    description = "Fails if any epistemic layer (master or per-layer) is off."
    tags = ["integration", "epistemic", "toggles"]
    player_role = "Detective"

    def setup(self):
        st = init_state()
        st.story = "iu_demo_epistemic"
        self.state = st
        return self.say_system("Initializing epistemic toggle scenario")

    @step(kind="action", description="Add truth fact")
    def add_truth(self):
        fact = EpistemicFact(
            id="truth_switch",
            content="Canonical truth exists when truth layer is enabled",
            subject="system",
            object=None,
            source="system",
            provenance="validated",
            confidence=1.0,
        )
        self.state.add_canonical_fact(fact)
        return self.say_llm("System", "Truth fact recorded")

    @step(kind="action", description="Add claim and observation")
    def add_claim_obs(self):
        claim = EpistemicClaim(
            id="claim_switch",
            content="Claim recorded when belief layer is enabled",
            subject="steve",
            object="iu",
            source="steve",
            provenance="testimony",
            confidence=0.5,
        )
        self.state.add_epistemic_claims(claim)
        self.state.record_observation(
            id="obs_switch",
            content="Observation recorded when belief layer is enabled",
            source="neighbor",
            provenance="observed",
            confidence=0.7,
        )
        return [
            self.say_user("Recording claim and observation"),
            self.say_llm("System", "Epistemic log updated"),
        ]

    @step(kind="action", description="Retrieval memory block")
    def retrieval_memory(self):
        block = _format_memory_block([
            {"type": "OBSERVED", "chunk_id": "chk1", "text": "Observed event"}
        ], "IU")
        return {"retrieval_block": block}

    @step(kind="assert", description="Validate layers active")
    def assert_layers(self):
        assert truth_enabled(), "Truth layer disabled"
        assert belief_enabled(), "Belief layer disabled"
        assert narrative_enabled(), "Narrative layer disabled"
        assert retrieval_enabled(), "Retrieval layer disabled"

        assert self.state.canonical_facts, "Expected canonical facts when truth layer on"
        assert self.state.epistemic_log, "Expected epistemic claims when belief layer on"
        assert self.state.observation_log, "Expected observations when belief layer on"

        # Retrieval block check
        block = _format_memory_block([
            {"type": "OBSERVED", "chunk_id": "chk1", "text": "Observed event"}
        ], "IU")
        assert block.strip(), "Expected retrieval memory block when retrieval layer on"


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

from backend.app.config.epistemic_flags import (
    belief_enabled,
    retrieval_enabled,
    narrative_enabled,
    truth_enabled,
)
from backend.app.engine import prompt_builder
from backend.app.engine.epistemic_state import EpistemicClaim, EpistemicFact
from backend.app.engine.state import init_state
from backend.app.integration_playback.scenario import IntegrationScenario, step


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
        return [self.say_user("Recording claim and observation"), self.say_llm("System", "Epistemic log updated")]

    @step(kind="action", description="Retrieval memory block")
    def retrieval_memory(self):
        block = prompt_builder._format_memory_block([
            {"type": "OBSERVED", "chunk_id": "chk1", "text": "Observed event"}
        ], "IU")
        return {"retrieval_block": block}

    @step(kind="assert", description="Validate layers active")
    def assert_layers(self):
        assert truth_enabled(), "Truth layer disabled"
        assert belief_enabled(), "Belief layer disabled"
        assert narrative_enabled(), "Narrative layer disabled"
        assert retrieval_enabled(), "Retrieval layer disabled"
        assert self.state.canonical_facts
        assert self.state.epistemic_log
        assert self.state.observation_log
        block = prompt_builder._format_memory_block([
            {"type": "OBSERVED", "chunk_id": "chk1", "text": "Observed event"}
        ], "IU")
        assert block.strip()

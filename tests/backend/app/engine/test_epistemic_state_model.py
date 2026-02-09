import pytest

from backend.app.engine.epistemic_state import (
    BeliefState,
    EpistemicClaim,
    EpistemicFact,
    EpistemicStatus,
    Observation,
)
from backend.app.engine.state import init_state


def test_epistemic_claim_clamps_confidence_and_formats_snippet():
    claim = EpistemicClaim(
        id="c1",
        content="Bob says he was never there",
        subject="bob",
        object="iu",
        source="bob",
        confidence=1.7,
        provenance="testimony",
        timestamp_minute=5,
        location_ref="steve_apartment",
    )

    assert claim.confidence == 1.0

    snippet = claim.as_prompt_snippet()
    assert "status=asserted" in snippet
    assert "prov=testimony" in snippet
    assert "conf=1.00" in snippet
    assert "loc=steve_apartment" in snippet
    assert "t=5" in snippet


def test_contested_and_resolved_conflict_states():
    c1 = EpistemicClaim(id="c1", content="Steve claims he left", source="steve")
    c2 = EpistemicClaim(id="c2", content="Bob says Steve never left", source="bob")

    c1.contested_with(c2)
    assert c1.status == EpistemicStatus.CONTESTED
    assert c2.status == EpistemicStatus.CONTESTED

    c1.resolve_conflict("Steve later confessed")
    assert c1.status == EpistemicStatus.RESOLVED
    assert "confessed" in (c1.resolution or "")


def test_belief_state_records_observations():
    beliefs = BeliefState(character_id="steve")

    obs = beliefs.record_observation(
        id="obs1",
        content="Neighbor heard arguing",
        timestamp_minute=50,
        location_ref="hallway",
        subject="steve",
        object="iu",
        source="neighbor",
        provenance="observed",
        confidence=0.8,
    )

    assert obs in beliefs.observations
    assert obs.status == EpistemicStatus.ASSERTED
    assert obs.confidence == 0.8


def test_state_has_epistemic_slots_and_belief_getter():
    st = init_state()
    assert st.canonical_facts == []
    assert st.epistemic_log == []
    assert st.observation_log == []

    belief_a = st.get_belief_state("bob")
    belief_b = st.get_belief_state("bob")

    assert belief_a is belief_b
    assert "bob" in st.beliefs

    obs = st.record_observation(
        id="global_obs",
        content="CCTV shows silhouette",
        timestamp_minute=45,
        location_ref="hallway_camera",
        source="system",
        provenance="observed",
    )
    assert obs in st.observation_log

    fact = EpistemicFact(id="f1", content="IU is deceased", source="system")
    st.add_canonical_fact(fact)
    assert st.canonical_facts[0].status == EpistemicStatus.ASSERTED

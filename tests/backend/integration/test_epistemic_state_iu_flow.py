import pytest

from backend.app.engine.epistemic_state import EpistemicClaim, EpistemicFact, EpistemicStatus
from backend.app.engine.state import init_state


@pytest.mark.integration
def test_epistemic_state_tracks_iu_case_without_api():
    """
    End-to-end (no API) check that the epistemic data model can represent the
    IU interrogation flow from the demo doc: denials, contradictions, and final
    confessions are all captured with statuses, observations, and canonical facts.
    """

    st = init_state()
    st.story = "iu_demo_epistemic"

    # Hidden truth (canonical) seeded up front.
    st.canonical_facts.append(
        EpistemicFact(
            id="truth_stabbing",
            content="Steve stabbed IU in the kitchen",
            subject="steve",
            object="iu",
            source="system",
            provenance="validated",
            confidence=1.0,
            location_ref="kitchen",
            timestamp_minute=60,
        )
    )

    steve_belief = st.get_belief_state("steve")
    bob_belief = st.get_belief_state("bob")

    # Round 1: Both deny being with IU.
    deny_steve = EpistemicClaim(
        id="r1_steve_denial",
        content="Steve claims IU never arrived and he was alone",
        subject="steve",
        object="iu",
        source="steve",
        provenance="testimony",
        confidence=0.6,
        location_ref="apartment",
        timestamp_minute=10,
    )
    deny_bob = EpistemicClaim(
        id="r1_bob_denial",
        content="Bob claims he was driving and never saw IU",
        subject="bob",
        object="iu",
        source="bob",
        provenance="testimony",
        confidence=0.6,
        location_ref="car",
        timestamp_minute=10,
    )
    steve_belief.add_claim(deny_steve)
    bob_belief.add_claim(deny_bob)
    st.epistemic_log.extend([deny_steve, deny_bob])

    # Observations the detective can cite.
    st.record_observation(
        id="obs_neighbor",
        content="Neighbor heard a man and a woman arguing around 11:50",
        source="neighbor",
        provenance="observed",
        confidence=0.7,
        location_ref="hallway",
        timestamp_minute=50,
    )
    st.record_observation(
        id="obs_cctv",
        content="Hallway camera shows a male silhouette entering at 11:45",
        source="system",
        provenance="observed",
        confidence=0.9,
        location_ref="hallway_camera",
        timestamp_minute=45,
    )

    # Round 3: Contradictions emerge (contest both claims).
    steve_round3 = EpistemicClaim(
        id="r3_steve_blame_bob",
        content="Steve admits Bob visited but says he stepped out before anything happened",
        subject="steve",
        object="bob",
        source="steve",
        provenance="testimony",
        confidence=0.55,
        location_ref="kitchen",
        timestamp_minute=70,
    )
    bob_round3 = EpistemicClaim(
        id="r3_bob_refutes_exit",
        content="Bob says Steve never left and was blocking the kitchen",
        subject="bob",
        object="steve",
        source="bob",
        provenance="testimony",
        confidence=0.6,
        location_ref="kitchen",
        timestamp_minute=70,
    )
    steve_round3.contested_with(bob_round3)
    st.epistemic_log.extend([steve_round3, bob_round3])
    steve_belief.add_claim(steve_round3)
    bob_belief.add_claim(bob_round3)

    # Round 4: Confessions resolve the conflict.
    steve_confession = EpistemicClaim(
        id="r4_steve_confesses",
        content="Steve confesses he stabbed IU; Bob took the knife to dispose of it",
        subject="steve",
        object="iu",
        source="steve",
        provenance="testimony",
        confidence=0.95,
        location_ref="kitchen",
        timestamp_minute=90,
    ).resolve_conflict("Confession recorded by detective")

    bob_coverup = EpistemicClaim(
        id="r4_bob_coverup",
        content="Bob admits wiping surfaces and throwing the knife off a bridge",
        subject="bob",
        object="iu",
        source="bob",
        provenance="testimony",
        confidence=0.9,
        location_ref="bridge",
        timestamp_minute=92,
    ).resolve_conflict("Bob corroborates cover-up details")

    st.epistemic_log.extend([steve_confession, bob_coverup])
    steve_belief.add_claim(steve_confession)
    bob_belief.add_claim(bob_coverup)

    st.canonical_facts.append(
        EpistemicFact(
            id="truth_coverup",
            content="Bob removed the knife and wiped surfaces after the stabbing",
            subject="bob",
            object="iu",
            source="system",
            provenance="validated",
            confidence=1.0,
            location_ref="kitchen",
            timestamp_minute=92,
            status=EpistemicStatus.RESOLVED,
        )
    )

    contested = [c for c in st.epistemic_log if c.status == EpistemicStatus.CONTESTED]
    resolved = [c for c in st.epistemic_log if c.status == EpistemicStatus.RESOLVED]

    assert len(st.observation_log) == 2
    assert contested, "Expected contested claims when accounts diverge"
    assert len(resolved) >= 2, "Confessions should move claims to resolved"
    assert st.canonical_facts, "Truth graph should hold canonical facts"
    assert st.beliefs["steve"].claims
    assert st.beliefs["bob"].claims

    confession_snippets = [c.as_prompt_snippet() for c in st.epistemic_log if "confesses" in c.content.lower()]
    assert any("resolved" in snippet for snippet in confession_snippets)

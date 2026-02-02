"""Scenario definition for epistemic IU flow (playback + pytest).

This mirrors the logic in test_epistemic_state_iu_flow but exposes a
structured Scenario for UI playback and programmatic execution.
"""

from backend.app.engine.epistemic_state import EpistemicClaim, EpistemicFact, EpistemicStatus
from backend.app.engine.state import init_state
from backend.app.integration_playback.scenario import Scenario, Step
from backend.app.integration_playback.scenario_registry import register_scenario


def _init_state():
    st = init_state()
    st.story = "iu_demo_epistemic"
    return {
        "state": st,
        "story": st.story,
        "reply": "Detective opens the IU case file and syncs the evidence board.",
        "debug": {"story": st.story},
    }


def _seed_truth(state):
    fact = EpistemicFact(
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
    state.canonical_facts.append(fact)
    return {
        "reply": "System pins canonical truth: Steve stabbed IU in the kitchen.",
        "debug": {"canonical_facts": [fact.content]},
    }


def _round1_denials(state):
    steve_belief = state.get_belief_state("steve")
    bob_belief = state.get_belief_state("bob")

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
    state.epistemic_log.extend([deny_steve, deny_bob])
    return [
        {"user": "Detective", "reply": "Steve, where were you when IU arrived?"},
        {"user": "Steve", "reply": "IU never even arrived. I was alone."},
        {"user": "Detective", "reply": "Bob, your turn—were you with her?"},
        {"user": "Bob", "reply": "I was driving all night, never saw IU."},
        {"steve_claim": deny_steve.content, "bob_claim": deny_bob.content},
    ]


def _add_observations(state):
    obs1 = state.record_observation(
        id="obs_neighbor",
        content="Neighbor heard a man and a woman arguing around 11:50",
        source="neighbor",
        provenance="observed",
        confidence=0.7,
        location_ref="hallway",
        timestamp_minute=50,
    )
    obs2 = state.record_observation(
        id="obs_cctv",
        content="Hallway camera shows a male silhouette entering at 11:45",
        source="system",
        provenance="observed",
        confidence=0.9,
        location_ref="hallway_camera",
        timestamp_minute=45,
    )
    return [
        {"user": "Detective", "reply": "Any witnesses or footage?"},
        "Neighbor whispers about an argument near midnight.",
        "CCTV shows a shadow slipping in earlier.",
        {"observations": [getattr(obs1, "content", None), getattr(obs2, "content", None)]},
    ]


def _round3_contradictions(state):
    steve_belief = state.get_belief_state("steve")
    bob_belief = state.get_belief_state("bob")

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
    state.epistemic_log.extend([steve_round3, bob_round3])
    steve_belief.add_claim(steve_round3)
    bob_belief.add_claim(bob_round3)
    return [
        {"user": "Detective", "reply": "Stories don’t align—clarify what happened."},
        {"user": "Steve", "reply": "Bob did swing by, but I stepped out before anything happened."},
        {"user": "Bob", "reply": "Steve never left—he was blocking the kitchen the whole time."},
        {"steve_contradiction": steve_round3.content, "bob_contradiction": bob_round3.content},
    ]


def _round4_confessions(state):
    steve_belief = state.get_belief_state("steve")
    bob_belief = state.get_belief_state("bob")

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

    state.epistemic_log.extend([steve_confession, bob_coverup])
    steve_belief.add_claim(steve_confession)
    bob_belief.add_claim(bob_coverup)

    state.canonical_facts.append(
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
    return [
        {"user": "Detective", "reply": "Steve, final chance—what really happened?"},
        {"user": "Steve", "reply": "I stabbed IU. Bob took the knife to dump it."},
        {"user": "Bob", "reply": "I wiped everything and tossed the knife off a bridge."},
        {"steve_confession": steve_confession.content, "bob_coverup": bob_coverup.content},
    ]


def _assert_epistemic(state):
    contested = [c for c in state.epistemic_log if c.status == EpistemicStatus.CONTESTED]
    resolved = [c for c in state.epistemic_log if c.status == EpistemicStatus.RESOLVED]

    assert len(state.observation_log) == 2
    assert contested, "Expected contested claims when accounts diverge"
    assert len(resolved) >= 2, "Confessions should move claims to resolved"
    assert state.canonical_facts, "Truth graph should hold canonical facts"
    assert state.beliefs["steve"].claims
    assert state.beliefs["bob"].claims
    return {
        "reply": "Board check: contested threads resolved, truths pinned.",
        "debug": {
            "canonical_facts": [f.content for f in state.canonical_facts],
            "contested": len(contested),
            "resolved": len(resolved),
        },
    }


# Build scenario
_epistemic_steps = [
    Step(kind="action", description="Init state", fn=_init_state, uses_llm=False),
    Step(kind="action", description="Seed truth", fn=_seed_truth, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Round 1 denials", fn=_round1_denials, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Add observations", fn=_add_observations, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Round 3 contradictions", fn=_round3_contradictions, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Round 4 confessions", fn=_round4_confessions, kwargs={"state": None}, uses_llm=False),
    Step(kind="assert", description="Validate epistemic state", fn=_assert_epistemic, kwargs={"state": None}, uses_llm=False),
]

SCENARIO_EPISTEMIC_IU = Scenario(
    id="epistemic_iu_flow",
    title="Epistemic IU interrogation flow",
    description="Deterministic epistemic log progression with denials, contradictions, confessions (no API calls).",
    tags=["integration", "epistemic", "cached"],
    requires_api_key=False,
    requires_cache=False,
    steps=_epistemic_steps,
)

register_scenario(SCENARIO_EPISTEMIC_IU)
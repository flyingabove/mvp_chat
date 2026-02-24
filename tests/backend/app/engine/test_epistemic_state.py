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


"""Scenario definition for epistemic IU flow (playback + pytest).

This mirrors the logic in test_epistemic_state_iu_flow but exposes a
structured Scenario for UI playback and programmatic execution.
"""

from backend.app.engine.epistemic_state import EpistemicClaim, EpistemicFact, EpistemicStatus
from backend.app.engine.state import init_state
from backend.app.integration_playback.scenario import IntegrationScenario, step


class EpistemicIUScenario(IntegrationScenario):
    scenario_id = "epistemic_iu_flow"
    title = "Epistemic: a believable interrogation flow (denials \u2192 contradictions \u2192 confessions)"
    description = (
        "A more conversational, story-like walkthrough that still exercises the exact same epistemic machinery. "
        "No API calls\u2014just deterministic updates to beliefs, observations, contested claims, and resolved truths."
    )
    tags = ["integration", "epistemic", "cached"]
    player_role = "Detective"

    def setup(self):
        st = init_state()
        st.story = "iu_demo_epistemic"
        self.state = st
        return {
            "reply": (
                "*The detective flips open the case file, takes a breath, and starts pinning notes to the board.*"
            ),
            **self.debug_info({"story": st.story}),
        }

    @step(kind="action", description="Seed truth")
    def seed_truth(self):
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
        self.state.add_canonical_fact(fact)
        return {
            "reply": (
                "*A verified fact gets pinned to the board.* "
                "\"Steve stabbed IU in the kitchen.\"\n\n"
                "*(The ink is still fresh, but the truth is already cold.)*"
            ),
            **self.debug_info({"canonical_facts": [fact.content]}),
        }

    @step(kind="action", description="Round 1 denials")
    def round1_denials(self):
        steve_belief = self.state.get_belief_state("steve")
        bob_belief = self.state.get_belief_state("bob")

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
        self.state.add_epistemic_claims(deny_steve, deny_bob)
        return [
            self.say_user("Walk me through your night. Start at 10."),
            self.say_llm("Steve", "Stayed in. Watched TV. IU didn't come over."),
            self.say_user("Last time you saw her?"),
            self.say_llm("Steve", "Yesterday. We're not great right now."),
            self.say_user("Bob here tonight?"),
            self.say_llm("Steve", "No. Haven't seen Bob today."),
            self.say_user("Any reason IU would show up late?"),
            self.say_llm("Steve", "No. She had her own place. She wasn't here."),

            self.say_user("Walk me through your night."),
            self.say_llm("Bob", "Drove around. Cleared my head. I didn't see IU."),
            self.say_user("Were you at Steve's?"),
            self.say_llm("Bob", "No."),
            self.say_user("You talk to Steve today?"),
            self.say_llm("Bob", "Texted. Nothing serious."),
            self.say_user("You two ever argue with IU?"),
            self.say_llm("Bob", "No. That was Steve's relationship."),
            self.debug_info({"steve_claim": deny_steve.content, "bob_claim": deny_bob.content}),
        ]

    @step(kind="action", description="Add observations")
    def add_observations(self):
        obs1 = self.state.record_observation(
            id="obs_neighbor",
            content="Neighbor heard a man and a woman arguing around 11:50",
            source="neighbor",
            provenance="observed",
            confidence=0.7,
            location_ref="hallway",
            timestamp_minute=50,
        )
        obs2 = self.state.record_observation(
            id="obs_cctv",
            content="Hallway camera shows a male silhouette entering at 11:45",
            source="system",
            provenance="observed",
            confidence=0.9,
            location_ref="hallway_camera",
            timestamp_minute=45,
        )
        return [
            self.say_user("IU's phone was active near your building late. You sure she didn't come by?"),
            self.say_llm("Steve", "Phones ping towers. Doesn't mean anything."),
            self.say_user("Neighbor heard arguing around 11:50. A woman crying."),
            self.say_llm("Steve", "Thin walls. Could be anyone."),
            self.say_user("Did Bob come over?"),
            self.say_llm("Steve", "No."),
            self.say_llm("System", "*Hallway camera shows a male silhouette entering at 11:45.*"),
            self.debug_info({"observations": [getattr(obs1, "content", None), getattr(obs2, "content", None)]}),
        ]

    @step(kind="action", description="Round 3 contradictions")
    def round3_contradictions(self):
        steve_belief = self.state.get_belief_state("steve")
        bob_belief = self.state.get_belief_state("bob")

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
        self.state.add_epistemic_claims(steve_round3, bob_round3)
        steve_belief.add_claim(steve_round3)
        bob_belief.add_claim(bob_round3)
        return [
            self.say_user("Bob's car was near your building at 11:46."),
            self.say_llm("Steve", "He drives everywhere."),
            self.say_user("He didn't deny being near. He denied being inside."),
            self.say_llm("Steve", "...So?"),
            self.say_user("Bob is positioning himself. He says you were worked up and asks what cooperation looks like."),
            self.say_llm("Steve", "Fine. Bob came by for a minute."),
            self.say_user("Inside?"),
            self.say_llm("Steve", "Yeah. Brief. But I left before things got bad."),
            self.say_user("You left your own apartment?"),
            self.say_llm("Steve", "I stepped out. Air. I didn't kill her."),

            self.say_user("Steve admits you were there."),
            self.say_llm("Bob", "...What?"),
            self.say_user("He says you came inside. He says he left before things got bad."),
            self.say_llm("Bob", "I was there, yes. But I didn't do anything. I walked in and felt something was off. Steve and IU were arguing. Steve was blocking the kitchen."),
            self.say_user("Did Steve leave?"),
            self.say_llm("Bob", "No. That's a lie. He didn't leave. He was right there."),
            self.debug_info({"steve_contradiction": steve_round3.content, "bob_contradiction": bob_round3.content}),
        ]

    @step(kind="action", description="Round 4 confessions")
    def round4_confessions(self):
        steve_belief = self.state.get_belief_state("steve")
        bob_belief = self.state.get_belief_state("bob")

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

        self.state.add_epistemic_claims(steve_confession, bob_coverup)
        steve_belief.add_claim(steve_confession)
        bob_belief.add_claim(bob_coverup)

        self.state.add_canonical_fact(
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
            self.say_user("He says you never left. He also says he's willing to cooperate."),
            self.say_llm("Steve", "She came at me with accusations. She had papers. She was screaming. I grabbed her arm to calm her down. It got out of control."),
            self.say_user("Did you stab IU?"),
            self.say_llm("Steve", "...I didn't mean to. It was a moment."),
            self.say_user("Where's the knife?"),
            self.say_llm("Steve", "Bob took it. He said he'd fix it."),

            self.say_user("Steve confessed. He says you took the knife."),
            self.say_llm("Bob", "I didn't stab her. But yes after it happened, Steve panicked. I wiped things. I took the knife. I threw it off a bridge."),
            self.say_user("Why help him?"),
            self.say_llm("Bob", "Because if I didn't, he'd say I did it. Exactly like he tried just now."),
            self.debug_info({"steve_confession": steve_confession.content, "bob_coverup": bob_coverup.content}),
        ]

    @step(kind="assert", description="Validate epistemic state")
    def assert_epistemic(self):
        contested = [c for c in self.state.epistemic_log if c.status == EpistemicStatus.CONTESTED]
        resolved = [c for c in self.state.epistemic_log if c.status == EpistemicStatus.RESOLVED]

        assert len(self.state.observation_log) == 2
        assert contested, "Expected contested claims when accounts diverge"
        assert len(resolved) >= 2, "Confessions should move claims to resolved"
        assert self.state.canonical_facts, "Truth graph should hold canonical facts"
        assert self.state.beliefs["steve"].claims
        assert self.state.beliefs["bob"].claims
        return {
            "reply": (
                "*The board is complete. Contradictions surfaced, confessions logged, and verified truths pinned cleanly.*\n\n"
                "*(The case is closed.)*"
            ),
            **self.debug_info({
                "canonical_facts": [f.content for f in self.state.canonical_facts],
                "contested": len(contested),
                "resolved": len(resolved),
            }),
        }


# -- Pytest entry point --
import pytest  # noqa: E402

@pytest.mark.integration
def test_epistemic_state_tracks_iu_case_without_api():
    EpistemicIUScenario.run_as_test()

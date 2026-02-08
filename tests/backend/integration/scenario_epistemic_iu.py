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
        self.state.canonical_facts.append(fact)
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
        self.state.epistemic_log.extend([deny_steve, deny_bob])
        return [
            {"user": "Detective", "reply": "*The detective leans forward, eyes narrowing.* \"Steve\u2014walk me through your night. When did IU get there?\""},
            {"user": "Steve", "reply": "*Steve shifts in his seat.* \"She didn't. IU never arrived. I was alone.\""},
            {"user": "Detective", "reply": "*The detective turns slowly.* \"Bob, I need your version too. Were you with IU at any point?\""},
            {"user": "Bob", "reply": "*Bob stares at the table.* \"No. I was driving all night. I never saw IU.\""},
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
            {"user": "Detective", "reply": "*The detective slaps the folder on the desk.* \"Alright. Any witnesses? Any cameras? Give me something concrete.\""},
            {"user": "Neighbor", "reply": "*A neighbor quietly mentions hearing a man and a woman arguing close to midnight.*"},
            {"user": "System", "reply": "*The hallway camera catches a dark silhouette entering earlier than that.*"},
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
        self.state.epistemic_log.extend([steve_round3, bob_round3])
        steve_belief.add_claim(steve_round3)
        bob_belief.add_claim(bob_round3)
        return [
            {"user": "Detective", "reply": "*The detective's voice drops.* \"Your stories don't line up. Slow down and tell me exactly what happened.\""},
            {"user": "Steve", "reply": "*Steve's jaw tightens.* \"Bob did stop by, but I stepped out before anything happened.\""},
            {"user": "Bob", "reply": "*Bob slams his hand on the table.* \"He's lying. Steve never left\u2014he was blocking the kitchen the whole time.\"\n\n*(The contradiction hangs in the air like smoke.)*"},
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

        self.state.epistemic_log.extend([steve_confession, bob_coverup])
        steve_belief.add_claim(steve_confession)
        bob_belief.add_claim(bob_coverup)

        self.state.canonical_facts.append(
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
            {"user": "Detective", "reply": "*The detective stands, casting a long shadow.* \"Steve\u2014last chance. What really happened in that kitchen?\""},
            {"user": "Steve", "reply": "*Steve's voice breaks.* \"I stabbed IU. Bob took the knife to get rid of it.\"\n\n*(His hands are shaking.)*"},
            {"user": "Bob", "reply": "*Bob exhales slowly.* \"I wiped things down and tossed the knife off a bridge.\""},
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

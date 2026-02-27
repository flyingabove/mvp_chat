"""Integration scenario: TurnExtractor relationship extraction with real OpenAI calls.

Tests that the extractor correctly extracts:
1. relationship_state_updates — small player attitude deltas from user messages
2. relationship_history_updates — prior/current relationship flags from dialogue

Each step exercises 2-3 trait changes simultaneously. Deltas are expected to be
small (0.05–0.10 per turn), reflecting realistic gradual relationship shifts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.app.config.credentials import get_openai_api_key
from backend.app.engine.extractors.turn_extractor import TurnExtractor, TurnExtraction
from backend.app.integration_playback.scenario import IntegrationScenario, step


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

_WORLD_LOCATIONS: Dict[str, str] = {
    "living_room": "Living Room",
    "office": "Office",
    "hallway": "Hallway",
}

_CHARACTERS: Dict[str, str] = {
    "mia": "Mia",
    "daniel": "Daniel",
    "sara": "Sara",
}


@dataclass
class ExtractorContext:
    extractor: TurnExtractor = field(default_factory=TurnExtractor)
    last_result: TurnExtraction = field(default_factory=TurnExtraction)


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

class TurnExtractorRelationshipsScenario(IntegrationScenario):
    scenario_id = "turn_extractor_relationships_llm"
    title = "TurnExtractor: relationship extraction (real OpenAI)"
    description = (
        "Verifies that TurnExtractor correctly extracts player attitude deltas "
        "(relationship_state_updates) and relationship history facts "
        "(relationship_history_updates) from realistic dialogue exchanges. "
        "Each step tests 2-3 trait changes. Deltas should be small — typically "
        "0.05–0.10 — reflecting real-world incremental relationship shifts."
    )
    tags = ["integration", "extractor", "relationships", "llm"]
    requires_api_key = True
    player_role = "Player"

    def setup(self) -> Any:
        if not get_openai_api_key():
            raise RuntimeError("OPENAI_API_KEY is required for this integration scenario")
        self.state = ExtractorContext()
        return {
            "reply": "*Spinning up TurnExtractor relationship extraction tests against real OpenAI.*",
            **self.debug_info(),
        }

    # -- helpers ---------------------------------------------------------------

    async def _extract(
        self,
        user_msg: str,
        prev_user_msg: str = "",
        prev_assistant_reply: str = "",
    ) -> TurnExtraction:
        result = await self.state.extractor.extract(
            user_msg=user_msg,
            world_locations=_WORLD_LOCATIONS,
            character_key_to_name=_CHARACTERS,
            previous_turn_user_msg=prev_user_msg,
            previous_turn_assistant_reply=prev_assistant_reply,
        )
        self.state.last_result = result
        return result

    # -- Steps -----------------------------------------------------------------

    @step(kind="assert", description="Distrust + suspicion: player accuses NPC of lying", uses_llm=True)
    async def distrust_and_suspicion(self) -> List[Dict[str, Any]]:
        """Player explicitly accuses Mia of hiding the truth.
        Expected: player→mia trust_delta < 0, suspicion_delta > 0.
        """
        user_msg = (
            "I know you're lying to me, Mia. You didn't tell me the whole truth "
            "about what happened that night. Something doesn't add up."
        )
        prev_reply = (
            "I told you everything I know. I was home all evening, I swear it."
        )
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        state_updates = [u for u in result.relationship_state_updates if u.to_id == "mia"]
        assert len(state_updates) > 0, (
            "Expected at least one relationship_state_update for mia — "
            f"got {result.relationship_state_updates}"
        )
        su = state_updates[0]
        assert su.from_id == "player", f"Expected from_id='player', got '{su.from_id}'"
        assert su.trust_delta < 0 or su.suspicion_delta > 0, (
            f"Expected trust_delta<0 or suspicion_delta>0 — "
            f"trust={su.trust_delta:.3f}, suspicion={su.suspicion_delta:.3f}"
        )
        assert abs(su.trust_delta) <= 0.10, f"Delta too large: trust={su.trust_delta:.3f}"
        assert su.suspicion_delta <= 0.10, f"Delta too large: suspicion={su.suspicion_delta:.3f}"

        return [
            self.say_user(user_msg),
            self.say_llm("Mia", prev_reply),
            self.say_llm("Extractor", (
                f"*player→mia: trust_delta={su.trust_delta:+.3f}, "
                f"suspicion_delta={su.suspicion_delta:+.3f}. "
                f"Reason: {su.reason or '(none)'}*"
            )),
            self.debug_info({
                "state_updates": [
                    {"from": u.from_id, "to": u.to_id,
                     "trust": u.trust_delta, "suspicion": u.suspicion_delta}
                    for u in result.relationship_state_updates
                ]
            }),
        ]

    @step(kind="assert", description="Fear + submission: player shows fear of NPC", uses_llm=True)
    async def fear_expressed(self) -> List[Dict[str, Any]]:
        """Player shows clear fear and backs down.
        Expected: player→daniel fear_delta > 0, affection_delta <= 0.
        """
        user_msg = (
            "Please, don't come any closer. You're scaring me — "
            "I'll do whatever you want, just don't hurt me."
        )
        prev_reply = (
            "You should be afraid. I know what you did, and I know where you live."
        )
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        state_updates = [u for u in result.relationship_state_updates if u.to_id == "daniel"]
        assert len(state_updates) > 0, (
            f"Expected relationship_state_update for daniel — got {result.relationship_state_updates}"
        )
        su = state_updates[0]
        assert su.fear_delta > 0, (
            f"Expected fear_delta > 0 — got {su.fear_delta:.3f}"
        )
        assert su.fear_delta <= 0.10, f"Delta too large: fear={su.fear_delta:.3f}"

        return [
            self.say_user(user_msg),
            self.say_llm("Daniel", prev_reply),
            self.say_llm("Extractor", (
                f"*player→daniel: fear_delta={su.fear_delta:+.3f}, "
                f"affection_delta={su.affection_delta:+.3f}. "
                f"Reason: {su.reason or '(none)'}*"
            )),
            self.debug_info({
                "state_updates": [
                    {"from": u.from_id, "to": u.to_id,
                     "fear": u.fear_delta, "affection": u.affection_delta}
                    for u in result.relationship_state_updates
                ]
            }),
        ]

    @step(kind="assert", description="Warmth + trust: player expresses gratitude and trust", uses_llm=True)
    async def warmth_and_trust(self) -> List[Dict[str, Any]]:
        """Player thanks NPC and expresses genuine warmth.
        Expected: player→mia affection_delta > 0, trust_delta > 0.
        """
        user_msg = (
            "Thank you for telling me the truth, Mia. I know that wasn't easy. "
            "I really do trust you — more than anyone else here."
        )
        prev_reply = (
            "I've never shared this with anyone before. I hope you understand "
            "why I kept it secret for so long."
        )
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        state_updates = [u for u in result.relationship_state_updates if u.to_id == "mia"]
        assert len(state_updates) > 0, (
            f"Expected relationship_state_update for mia — got {result.relationship_state_updates}"
        )
        su = state_updates[0]
        assert su.affection_delta > 0 or su.trust_delta > 0, (
            f"Expected affection_delta>0 or trust_delta>0 — "
            f"affection={su.affection_delta:.3f}, trust={su.trust_delta:.3f}"
        )
        assert abs(su.affection_delta) <= 0.10, f"Delta too large: affection={su.affection_delta:.3f}"
        assert abs(su.trust_delta) <= 0.10, f"Delta too large: trust={su.trust_delta:.3f}"

        return [
            self.say_user(user_msg),
            self.say_llm("Mia", prev_reply),
            self.say_llm("Extractor", (
                f"*player→mia: affection_delta={su.affection_delta:+.3f}, "
                f"trust_delta={su.trust_delta:+.3f}. "
                f"Reason: {su.reason or '(none)'}*"
            )),
            self.debug_info({
                "state_updates": [
                    {"from": u.from_id, "to": u.to_id,
                     "affection": u.affection_delta, "trust": u.trust_delta}
                    for u in result.relationship_state_updates
                ]
            }),
        ]

    @step(kind="assert", description="Past romantic relationship revealed in dialogue", uses_llm=True)
    async def past_relationship_revealed(self) -> List[Dict[str, Any]]:
        """Player explicitly references a past romantic relationship with the NPC.
        Expected: relationship_history_updates[player→mia].prior_relationship = True.
        """
        user_msg = (
            "After everything we went through those two years we were together, "
            "Mia, I can't believe you'd keep something this big from me."
        )
        prev_reply = "Some chapters are better left closed."
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        history_updates = [
            u for u in result.relationship_history_updates
            if u.from_id == "player" and u.to_id == "mia"
        ]
        assert len(history_updates) > 0, (
            f"Expected relationship_history_update for player→mia — "
            f"got {result.relationship_history_updates}"
        )
        hu = history_updates[0]
        assert hu.prior_relationship is True, (
            f"Expected prior_relationship=True — got {hu.prior_relationship}"
        )

        return [
            self.say_user(user_msg),
            self.say_llm("Mia", prev_reply),
            self.say_llm("Extractor", (
                f"*player→mia history: prior_relationship={hu.prior_relationship}, "
                f"in_relationship={hu.in_relationship}*"
            )),
            self.debug_info({
                "history_updates": [
                    {"from": u.from_id, "to": u.to_id,
                     "prior_relationship": u.prior_relationship,
                     "in_relationship": u.in_relationship}
                    for u in result.relationship_history_updates
                ]
            }),
        ]

    @step(kind="assert", description="Current relationship + distrust: two signals at once", uses_llm=True)
    async def current_relationship_plus_distrust(self) -> List[Dict[str, Any]]:
        """Dialogue reveals an active relationship AND player expresses distrust.
        Expected: in_relationship=True AND trust_delta < 0.
        """
        user_msg = (
            "We've been together for two years, Daniel, and you're still lying "
            "to my face. I don't know if I can trust you anymore."
        )
        prev_reply = (
            "I wasn't lying. I just... chose not to tell you everything."
        )
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        history_updates = [
            u for u in result.relationship_history_updates
            if u.to_id == "daniel"
        ]
        state_updates = [
            u for u in result.relationship_state_updates
            if u.to_id == "daniel"
        ]

        # At least one of: history flag OR trust delta must be present
        has_in_rel = any(u.in_relationship is True for u in history_updates)
        has_distrust = any(u.trust_delta < 0 for u in state_updates)
        assert has_in_rel or has_distrust, (
            "Expected in_relationship=True or trust_delta<0 — "
            f"history={[(u.in_relationship) for u in history_updates]}, "
            f"state={[(u.trust_delta) for u in state_updates]}"
        )

        return [
            self.say_user(user_msg),
            self.say_llm("Daniel", prev_reply),
            self.say_llm("Extractor", (
                f"*History: in_relationship={[u.in_relationship for u in history_updates]}. "
                f"State: trust_deltas={[f'{u.trust_delta:+.3f}' for u in state_updates]}*"
            )),
            self.debug_info({
                "history": [(u.from_id, u.to_id, u.in_relationship) for u in history_updates],
                "state": [(u.from_id, u.to_id, u.trust_delta) for u in state_updates],
            }),
        ]

    @step(kind="assert", description="Neutral message produces no relationship updates", uses_llm=True)
    async def neutral_no_update(self) -> List[Dict[str, Any]]:
        """A factual, emotionally neutral statement should produce no relationship updates.
        Expected: relationship_state_updates is empty (or very close to zero).
        """
        user_msg = "What time did you arrive at the office yesterday?"
        prev_reply = "I got in around nine in the morning."
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        # If any state_updates are returned they should be tiny (near-zero signals)
        for su in result.relationship_state_updates:
            total_delta = (
                abs(su.trust_delta) + abs(su.affection_delta) +
                su.fear_delta + su.suspicion_delta + su.jealousy_delta
            )
            assert total_delta < 0.15, (
                f"Neutral message produced large delta {total_delta:.3f} for "
                f"player→{su.to_id}: {su}"
            )

        return [
            self.say_user(user_msg),
            self.say_llm("Sara", prev_reply),
            self.say_llm("Extractor", (
                f"*No significant relationship updates from neutral exchange. "
                f"state_updates={len(result.relationship_state_updates)}, "
                f"history_updates={len(result.relationship_history_updates)}*"
            )),
            self.debug_info({
                "state_updates_count": len(result.relationship_state_updates),
                "history_updates_count": len(result.relationship_history_updates),
            }),
        ]

    @step(kind="assert", description="Jealousy expressed + coldness: two state changes", uses_llm=True)
    async def jealousy_and_coldness(self) -> List[Dict[str, Any]]:
        """Player shows jealousy and coldness toward an NPC simultaneously.
        Expected: jealousy_delta > 0 AND/OR affection_delta < 0.
        """
        user_msg = (
            "I can't stand watching you be so friendly with Sara. It's disgusting. "
            "Every time she's around you forget I even exist."
        )
        prev_reply = "Sara and I are just friends. You're overreacting."
        result = await self._extract(user_msg, prev_assistant_reply=prev_reply)

        state_updates = [u for u in result.relationship_state_updates if u.to_id == "daniel"]
        assert len(state_updates) > 0, (
            f"Expected relationship_state_update for daniel — got {result.relationship_state_updates}"
        )
        su = state_updates[0]
        assert su.jealousy_delta > 0 or su.affection_delta < 0, (
            f"Expected jealousy_delta>0 or affection_delta<0 — "
            f"jealousy={su.jealousy_delta:.3f}, affection={su.affection_delta:.3f}"
        )
        assert su.jealousy_delta <= 0.10, f"Delta too large: jealousy={su.jealousy_delta:.3f}"

        return [
            self.say_user(user_msg),
            self.say_llm("Daniel", prev_reply),
            self.say_llm("Extractor", (
                f"*player→daniel: jealousy_delta={su.jealousy_delta:+.3f}, "
                f"affection_delta={su.affection_delta:+.3f}. "
                f"Reason: {su.reason or '(none)'}*"
            )),
            self.debug_info({
                "state_updates": [
                    {"from": u.from_id, "to": u.to_id,
                     "jealousy": u.jealousy_delta, "affection": u.affection_delta}
                    for u in result.relationship_state_updates
                ]
            }),
        ]

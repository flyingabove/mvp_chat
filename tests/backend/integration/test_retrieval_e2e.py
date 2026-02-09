"""Playback scenario for character retrieval sanity check."""

import os
from dataclasses import dataclass

from backend.app.knowledge.runtime.load_indexes import load_character_indexes
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge
from backend.app.integration_playback.scenario import IntegrationScenario, step


@dataclass
class RetrievalContext:
    character_id: str = "1_iu"
    joined_text: str | None = None


class RetrievalE2EScenario(IntegrationScenario):
    scenario_id = "character_retrieval_e2e"
    title = "Character retrieval end-to-end"
    description = "Loads character indexes and retrieves real knowledge chunks for 'who are you'."
    tags = ["integration", "retrieval"]
    requires_cache = True
    player_role = "Detective"

    def setup(self):
        self.state = RetrievalContext(character_id=os.getenv("TEST_CHARACTER_ID", "1_iu"))
        return {
            "reply": "*Warming up the knowledge indexes\u2014pretend we're about to ask a real person 'who are you?'*",
            **self.debug_info({"character_id": self.state.character_id}),
        }

    @step(kind="assert", description="Run end-to-end retrieval")
    def run_retrieval(self):
        indexes = load_character_indexes(self.state.character_id)

        assert indexes.chunks, "No knowledge chunks loaded"
        assert len(indexes.chunks) > 0

        query = "who are you"
        chunks, _debug = retrieve_knowledge(query)

        assert chunks, "Retrieval returned no chunks"
        assert isinstance(chunks, list)

        joined_text = " ".join((c.get("text", "") or "").lower() for c in chunks)
        self.state.joined_text = joined_text
        assert len(joined_text) > 0, "Retrieved chunks have no text content"

        sample = (chunks[0].get("text", "") or "").strip() if chunks else ""
        sample = sample[:220]

        return [
            self.say_user("Before we start, who are you, really?"),
            self.say_system(f"*Pulled a quick dossier snippet:* \"{sample}\""),
            self.debug_info({"chunks": [c.get("text", "")[:100] for c in chunks[:3]], "query": query}),
        ]


# -- Pytest entry point --
import pytest  # noqa: E402

@pytest.mark.integration
def test_character_retrieval_returns_real_knowledge():
    RetrievalE2EScenario.run_as_test()

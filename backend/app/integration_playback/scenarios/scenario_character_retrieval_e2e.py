import os
from dataclasses import dataclass
from pathlib import Path

from backend.app.integration_playback.scenario import IntegrationScenario, step
from backend.app.knowledge.runtime.index_service import IndexService
from backend.app.knowledge.runtime.load_indexes import load_character_indexes
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge


def _default_character_id() -> str:
    env = os.getenv("TEST_CHARACTER_ID")
    if env:
        return env
    base_dir = Path(__file__).resolve().parents[2] / "knowledge" / "base"
    if base_dir.exists():
        for child in sorted(base_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("__"):
                return child.name
    return "iu"


@dataclass
class RetrievalContext:
    character_id: str = _default_character_id()
    joined_text: str | None = None


class RetrievalE2EScenario(IntegrationScenario):
    scenario_id = "character_retrieval_e2e"
    title = "Character retrieval end-to-end"
    description = "Loads character indexes and retrieves real knowledge chunks for who-are-you query."
    tags = ["integration", "retrieval"]
    requires_cache = True
    player_role = "Detective"

    def setup(self):
        self.state = RetrievalContext(character_id=os.getenv("TEST_CHARACTER_ID", _default_character_id()))
        IndexService.reset_for_tests()
        IndexService.set_active_character(self.state.character_id)
        return self.debug_info({"character_id": self.state.character_id})

    @step(kind="assert", description="Run end-to-end retrieval")
    def run_retrieval(self):
        indexes = load_character_indexes(self.state.character_id)
        IndexService.set_active_character(self.state.character_id)

        assert indexes.chunks
        query = "who are you"
        chunks, _debug = retrieve_knowledge(query)

        assert chunks
        joined_text = " ".join((c.get("text", "") or "").lower() for c in chunks)
        self.state.joined_text = joined_text
        assert len(joined_text) > 0

        return self.debug_info({"query": query, "chunks": [c.get("text", "")[:100] for c in chunks[:3]]})

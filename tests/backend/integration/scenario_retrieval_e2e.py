"""Playback scenario for character retrieval sanity check."""

import os
from dataclasses import dataclass

from backend.app.knowledge.runtime.load_indexes import load_character_indexes
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge
from backend.app.integration_playback.scenario import Scenario, Step
from backend.app.integration_playback.scenario_registry import register_scenario


@dataclass
class RetrievalContext:
    character_id: str = "1_iu"
    joined_text: str | None = None


def _init_context() -> RetrievalContext:
    ctx = RetrievalContext(character_id=os.getenv("TEST_CHARACTER_ID", "1_iu"))
    return {
        "state": ctx,
        "reply": "Warming up the knowledge indexes—pretend we're about to ask a real person 'who are you?'",
    }


def _run_retrieval(state: RetrievalContext):
    indexes = load_character_indexes(state.character_id)

    assert indexes.chunks, "No knowledge chunks loaded"
    assert len(indexes.chunks) > 0

    query = "who are you"
    chunks, _debug = retrieve_knowledge(query)

    assert chunks, "Retrieval returned no chunks"
    assert isinstance(chunks, list)

    joined_text = " ".join((c.get("text", "") or "").lower() for c in chunks)
    state.joined_text = joined_text
    assert len(joined_text) > 0, "Retrieved chunks have no text content"

    sample = (chunks[0].get("text", "") or "").strip() if chunks else ""
    sample = sample[:220]

    return [
        {"user": "Detective", "reply": "Before we start—who are you, really?"},
        {"user": "System", "reply": f"Pulled a quick dossier snippet: {sample}"},
        {"debug": {"chunks": chunks[:3], "query": query}},
    ]


steps = [
    Step(kind="action", description="Init retrieval context", fn=_init_context, uses_llm=False),
    Step(kind="assert", description="Run end-to-end retrieval", fn=_run_retrieval, kwargs={"state": None}, uses_llm=False),
]

SCENARIO_RETRIEVAL_E2E = Scenario(
    id="character_retrieval_e2e",
    title="Character retrieval end-to-end",
    description="Loads character indexes and retrieves real knowledge chunks for 'who are you'.",
    tags=["integration", "retrieval"],
    requires_api_key=False,
    requires_cache=True,
    steps=steps,
)

register_scenario(SCENARIO_RETRIEVAL_E2E)

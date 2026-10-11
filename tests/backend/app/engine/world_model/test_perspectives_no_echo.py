"""BL-47 part 2: a speaker's own old lines are not fed back as "what they personally remember".

Live beta 2026-09-29: after one refusal Minori kept answering unrelated turns with variants of it, and Hikaru
reused a line Minori had just said. Cause: dialogue memories (every spoken line, for the speaker and each
listener) matched the "@id" mention boost whenever the player named that character.
"""
from types import SimpleNamespace

from backend.app.engine.world_model.memory import MemoryStore
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model

REFUSAL = "@minori said: I want to take my time getting to know everyone, no big plans for now."
CFG = {"world_model": {"enabled": True}}


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=CFG,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=5, outcome=None)


def _model_after_a_refusal():
    model = make_model({"minori": "kitchen", "hikaru": "kitchen"})
    model.memories.add("minori", REFUSAL, "witnessed", 0, kind="dialogue")
    model.memories.add("hikaru", REFUSAL, "witnessed", 0, kind="dialogue")      # Hikaru heard it
    return model


def test_the_speakers_own_refusal_is_not_replayed_as_a_memory_on_an_unrelated_turn():
    model = _model_after_a_refusal()
    view = begin_turn(_state(model), "Minori, can I make you some breakfast?", 0)
    assert "minori" in view.plan.speakers or view.plan.speakers, "someone answers"
    remembered = " ".join(m for items in view.perspectives.values() for m in items)
    assert "take my time" not in remembered and "no big plans" not in remembered


def test_a_listener_does_not_get_the_line_someone_else_said_either():
    model = _model_after_a_refusal()
    view = begin_turn(_state(model), "Hikaru, Minori, what are you two up to today?", 0)
    for cid, items in view.perspectives.items():
        assert not any("take my time" in item for item in items), cid


def test_facts_and_promises_are_still_recalled():
    model = make_model({"minori": "kitchen"})
    model.memories.add("minori", "@player loves miso soup", "told_by:player", -30)
    model.memories.add("minori", REFUSAL, "witnessed", 0, kind="dialogue")
    view = begin_turn(_state(model), "Minori, shall I make miso soup?", 0)
    remembered = " ".join(m for items in view.perspectives.values() for m in items)
    assert "miso soup" in remembered and "take my time" not in remembered


def test_search_can_exclude_memories_and_defaults_to_everything():
    store = MemoryStore()
    store.add("ann", "@ann said: hello there friend", "witnessed", 0, kind="dialogue")
    store.add("ann", "friend of the house", "authored", 0, kind="fact")
    both = store.search("ann", "friend", mentions=["ann"], k=5)
    assert {m.kind for m in both} == {"dialogue", "fact"}
    facts_only = store.search("ann", "friend", mentions=["ann"], k=5, exclude=lambda m: m.kind == "dialogue")
    assert [m.kind for m in facts_only] == ["fact"]


def test_what_the_player_told_a_resident_is_still_recalled():
    model = make_model({"minori": "kitchen"})
    model.memories.add("minori", "@player said: I found a key under the mat", "told_by:player", -5, kind="dialogue")
    view = begin_turn(_state(model), "Minori, what do you think about the key under the mat?", 0)
    assert any("key under the mat" in line for line in view.perspectives.get("minori", []))

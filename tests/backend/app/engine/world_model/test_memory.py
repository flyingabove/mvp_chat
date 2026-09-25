"""Step 2: per-character memories, provenance, @id rendering, per-owner search."""
import pytest

from backend.app.engine.world_model.memory import Memory, MemoryStore, Ref, render


def test_every_memory_needs_a_channel():
    store = MemoryStore()
    for source in ("witnessed", "overheard", "authored", "promised", "told_by:ann"):
        store.add("ben", "x", source, 0)
    with pytest.raises(ValueError):
        store.add("ben", "x", "heard_somewhere", 0)
    with pytest.raises(ValueError):
        store.add("ben", "x", "told_by:", 0)


def test_at_ids_render_as_names_only_for_viewers_who_know_them():
    names = {"b": "Uchi", "a": "Arisa"}
    descriptors = {"b": "the hair stylist"}
    assert render("I argued with @b", names) == "I argued with Uchi"
    assert render("I argued with @b", names, known={"a"}, descriptors=descriptors) == "I argued with the hair stylist"
    assert render("@zed waved", names, known=set()) == "someone waved"


def test_descriptor_refs_never_render_their_hidden_actual_identity():
    store = MemoryStore()
    memory = store.add("c", "two people arguing near the fountain; one wore a blue jacket", "witnessed", 5,
                       confidence=0.7, refs=(Ref("person in a blue jacket", actual="b", identified=False),))
    rendered = render(memory.text, {"b": "Uchi"})
    assert "Uchi" not in rendered and "@b" not in rendered and "b" not in rendered.split()
    assert memory.refs[0].actual == "b"          # engine-only truth survives
    assert "b" not in memory.mentions()


def test_search_returns_only_the_owners_memories():
    store = MemoryStore()
    store.add("ann", "I love baseball practice", "witnessed", 1)
    store.add("ben", "baseball is boring", "witnessed", 2)
    assert [m.owner for m in store.search("ann", "baseball")] == ["ann"]
    assert store.search("cat", "baseball") == []


def test_search_ranks_mentioned_people_above_plain_word_matches():
    store = MemoryStore()
    store.add("ann", "the park was lovely in the rain", "witnessed", 1)
    store.add("ann", "@ben and I walked to the park", "witnessed", 2)
    store.add("ann", "cooking dinner tonight", "witnessed", 3)
    found = store.search("ann", "what about the park with Ben?", mentions={"ben"}, k=2)
    assert found[0].text == "@ben and I walked to the park"
    assert all("cooking" not in m.text for m in found)


def test_search_breaks_ties_by_recency_and_respects_kinds():
    store = MemoryStore()
    store.add("ann", "rain again", "witnessed", 1)
    store.add("ann", "rain again", "witnessed", 9)
    store.add("ann", "rain lore", "authored", 0, kind="lore")
    assert store.search("ann", "rain", k=1)[0].minute == 9
    assert [m.kind for m in store.search("ann", "rain", kinds=["lore"])] == ["lore"]


def test_confidence_is_clamped_and_unknown_kinds_rejected():
    assert Memory("M1", "a", "x", "witnessed", 0, confidence=3.0).confidence == 1.0
    with pytest.raises(ValueError):
        Memory("M1", "a", "x", "witnessed", 0, kind="dream")


def test_open_promises_and_knowledge_queries():
    store = MemoryStore()
    store.add("ann", "I promised @player to cook", "promised", 1, kind="promise", due=100, counterpart="player")
    store.add("ann", "saw a fox", "witnessed", 2, event_id="E7")
    assert len(store.open_promises("ann")) == 1 and store.open_promises("ben") == []
    assert store.knows_event("ann", "E7") and not store.knows_event("ben", "E7")
    assert store.has_text("ann", "saw a fox")


def test_store_round_trip_keeps_counter_so_ids_never_collide():
    store = MemoryStore()
    store.add("ann", "one", "witnessed", 1)
    restored = MemoryStore.from_dict(store.to_dict())
    assert restored.add("ann", "two", "witnessed", 2).id == "M2"
    assert restored.memories[0].to_dict() == store.memories[0].to_dict()

"""Steps 7-8: contact channel and evidence inspection."""
from backend.app.engine.world_model.commitments import add_commitment
from backend.app.engine.world_model.contact import deliver, queue_contacts
from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.evidence import find_inspect_target, inspect
from backend.app.engine.world_model.memory import render
from backend.app.engine.world_model.model import PLAYER
from tests.backend.app.engine.world_model.helpers import make_model


def test_a_due_promise_to_the_player_triggers_a_message_when_apart():
    model = make_model({"ann": "office", "ben": "kitchen"})
    add_commitment(model, "ann", PLAYER, "call about dinner", due=50, minute=0)
    queued = queue_contacts(model, 0, 60)
    assert [c.sender for c in queued] == ["ann"] and "promise" in queued[0].intent
    assert model.memories.search("ann", "texted", k=1)[0].kind == "contact"


def test_no_message_when_together_asleep_or_without_reason():
    model = make_model({"ann": "kitchen", "ben": "office"})
    add_commitment(model, "ann", PLAYER, "call", due=50, minute=0)
    model.characters["ben"].availability = "asleep"
    add_commitment(model, "ben", PLAYER, "call", due=50, minute=0)
    assert queue_contacts(model, 0, 60) == []           # ann is with the player, ben asleep
    assert queue_contacts(make_model({"cat": "office"}), 0, 60) == []


def test_warm_check_ins_are_rare_and_at_most_daily():
    model = make_model({f"p{i}": "office" for i in range(40)})
    queued = queue_contacts(model, 0, 60, warmth=lambda cid: 1.0)
    assert 0 < len(queued) < 40                        # seeded 25% chance
    again = queue_contacts(model, 60, 120, warmth=lambda cid: 1.0)
    assert not ({c.sender for c in again} & {c.sender for c in queued})


def test_delivery_happens_once_and_waits_while_the_player_sleeps():
    model = make_model({"ann": "office"})
    add_commitment(model, "ann", PLAYER, "call", due=50, minute=0)
    queue_contacts(model, 0, 60)
    model.player_availability = "asleep"
    assert deliver(model) == []
    model.player_availability = "awake"
    assert len(deliver(model)) == 1 and deliver(model) == []


def _room_with_closet():
    model = make_model({"ann": "apartment"}, player_place="apartment")
    closet = Entity("closet_scuff", "evidence", "closet", aliases=["jamb", "scratches"], props={"surfaces": [
        {"text": "faint scratches beneath the paint"},
        {"text": "the marks look older than one night", "requires": {"attention": "close"}},
        {"text": "a fiber caught in the hinge", "requires": {"tool": "flashlight"}}]})
    model.world.entities[closet.id] = closet
    model.world.move(closet.id, "apartment")
    return model, closet


def test_inspection_returns_only_perceivable_surfaces_and_records_memories():
    model, closet = _room_with_closet()
    assert find_inspect_target(model, "I examine the closet") is closet
    glance = inspect(model, closet, "I examine the closet", witnesses=("ann",))
    assert glance.noticed == ["faint scratches beneath the paint"] and glance.missed == 2
    close = inspect(model, closet, "I look closely at the jamb")
    assert "the marks look older than one night" in close.noticed
    assert model.memories.search(PLAYER, "closet scratches", k=5)
    assert model.memories.search("ann", "examined closet", k=1)


def test_tools_carried_by_the_player_unlock_surfaces():
    model, closet = _room_with_closet()
    model.world.entities["flashlight"] = Entity("flashlight", "object", "flashlight")
    model.world.move("flashlight", PLAYER)
    assert "a fiber caught in the hinge" in inspect(model, closet, "check the closet").noticed


def test_absent_evidence_cannot_be_inspected_and_plain_talk_is_not_inspection():
    model, closet = _room_with_closet()
    assert find_inspect_target(model, "What do you think about the closet?") is None
    model.world.move(PLAYER, "hallway")
    assert find_inspect_target(model, "I examine the closet") is None


def test_hidden_truth_links_are_never_rendered():
    model, closet = _room_with_closet()
    closet.props["truth_event"] = "E99"
    inspect(model, closet, "I examine the closet")
    for memory in model.memories.of(PLAYER):
        assert "E99" not in render(memory.text, model.names())

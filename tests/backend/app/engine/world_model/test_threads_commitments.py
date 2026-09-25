"""Step 5: personal threads and remembered promises."""
from backend.app.engine.world_model.commitments import (add_commitment, due_commitments, record_commitment,
                                                         due_minute, expire_commitments)
from backend.app.engine.world_model.model import PLAYER
from backend.app.engine.world_model.threads import Milestone, Thread, advance_threads
from tests.backend.app.engine.world_model.helpers import make_model


def _thread():
    return Thread("audition", "ann", "The audition", topics=["ballet"], milestones=[
        Milestone("m1", 1, "13:00", "@ann's teacher corrected her turns", memory_for=["ben"]),
        Milestone("m2", 2, "07:30", "@ann taped a schedule to the fridge", "public",
                  trace="A schedule is taped to the fridge", place="kitchen"),
        Milestone("m3", 4, "10:00", "@ann's audition moved up"),
    ])


def test_milestones_fire_once_in_order_across_a_long_skip():
    model = make_model({"ann": "living_room", "ben": "kitchen", "cat": "kitchen"})
    model.threads.append(_thread())
    fired = advance_threads(model, 0, model.world.absolute_minute(3, "00:00"))
    assert [m.id for _, m in fired] == ["m1", "m2"]
    assert advance_threads(model, 0, model.world.absolute_minute(3, "00:00")) == []
    assert [m.id for _, m in advance_threads(model, 0, model.world.absolute_minute(5, "00:00"))] == ["m3"]


def test_milestone_memories_go_only_to_owner_and_memory_for_and_are_private():
    model = make_model({"ann": "living_room", "ben": "kitchen", "cat": "kitchen"})
    model.threads.append(_thread())
    advance_threads(model, 0, model.world.absolute_minute(1, "14:00"))
    assert model.memories.of("ann")[0].private and model.memories.of("ben")
    assert model.memories.of("cat") == []
    assert model.world.events[0].kind == "milestone"


def test_public_milestone_leaves_a_trace_at_its_place():
    model = make_model({"ann": "living_room"})
    model.threads.append(_thread())
    advance_threads(model, 0, model.world.absolute_minute(2, "08:00"))
    trace = model.traces[-1]
    assert trace.place == "kitchen" and trace.text == "A schedule is taped to the fridge"
    assert trace.visible(model.world.absolute_minute(2, "09:00"), "kitchen", set())
    assert not trace.visible(model.world.absolute_minute(2, "09:00"), "terrace", set())


def test_threads_of_characters_not_in_the_world_do_not_advance():
    model = make_model({"ben": "kitchen"})
    model.threads.append(_thread())
    assert advance_threads(model, 0, 10 * 1440) == []


def test_extracted_commitments_are_recorded_once_for_both_parties():
    model = make_model({"ann": "kitchen"})
    made = record_commitment(model, "ann", PLAYER, "save you a plate of dinner", "tonight", 10)
    assert made is not None and made.due == model.world.absolute_minute(0, "20:00")
    assert record_commitment(model, "ann", PLAYER, "save you a plate of dinner", "tonight", 12) is None  # dedupe
    theirs = model.memories.of(PLAYER)
    assert theirs and theirs[0].source == "told_by:ann" and theirs[0].kind == "promise"


def test_commitments_between_unknown_people_are_ignored():
    model = make_model({"ann": "kitchen"})
    assert record_commitment(model, "ghost", PLAYER, "x", "later", 0) is None
    assert record_commitment(model, "ann", "ann", "x", "later", 0) is None
    assert record_commitment(model, "ann", PLAYER, "  ", "later", 0) is None


def test_due_minute_phrases():
    model = make_model({})
    w = model.world
    assert due_minute(model, "tomorrow morning", 0) == w.absolute_minute(1, "09:00")
    assert due_minute(model, "tomorrow evening", 0) == w.absolute_minute(1, "19:00")
    assert due_minute(model, "at 9pm", 0) == w.absolute_minute(0, "21:00")
    assert due_minute(model, "at 8", 0) == w.absolute_minute(1, "08:00")
    assert due_minute(model, "after dinner", 30) == 120
    assert due_minute(model, "later", 30) == 210
    assert due_minute(model, "tomorrow at 8pm", 0) == w.absolute_minute(1, "20:00")
    assert due_minute(model, "this weekend", 0) == w.absolute_minute(3, "12:00")      # Wed -> Sat
    assert due_minute(model, "Tomorrow Morning", 0) == w.absolute_minute(1, "09:00")
    assert due_minute(model, "in the morning", 0) == w.absolute_minute(1, "09:00")
    assert due_minute(model, "whenever", 30) == 210


def test_due_and_expired_commitments():
    model = make_model({"ann": "kitchen"})
    own, _ = add_commitment(model, "ann", PLAYER, "cook curry", due=100, minute=0)
    assert due_commitments(model, 50) == []
    assert due_commitments(model, 100) == [own]
    expired = expire_commitments(model, 100 + 12 * 60)
    assert own in expired and {m.owner for m in expired} == {"ann", PLAYER}     # both sides' copies
    assert all(m.status == "broken" for m in expired)
    assert due_commitments(model, 100 + 12 * 60) == []


# --- live QC round 2 (extractor commitments): owner flips, meal times, near-duplicates ---

def test_a_request_recorded_as_the_players_own_promise_is_flipped_to_the_doer():
    model = make_model({"minori": "kitchen"})
    made = record_commitment(model, PLAYER, "minori", "show me around the terrace", "tomorrow morning", 0)
    assert made.owner == "minori" and made.counterpart == PLAYER
    assert "show you around the terrace" in made.text


def test_meal_words_set_the_due_time_when_the_phrase_has_no_clock():
    model = make_model({"ann": "kitchen"})
    w = model.world
    assert record_commitment(model, "ann", PLAYER, "save you some dinner", "tomorrow", 0).due == w.absolute_minute(1, "19:00")
    assert record_commitment(model, "ann", PLAYER, "make you breakfast", "tomorrow", 0).due == w.absolute_minute(1, "08:00")
    assert record_commitment(model, "ann", PLAYER, "grab lunch together", "tomorrow at 1pm", 0).due == w.absolute_minute(1, "13:00")


def test_near_duplicate_promises_are_recorded_once():
    model = make_model({"ann": "kitchen"})
    assert record_commitment(model, "ann", PLAYER, "save you some dinner", "tonight", 0) is not None
    assert record_commitment(model, "ann", PLAYER, "save you dinner", "tonight", 1) is None
    assert record_commitment(model, "ann", PLAYER, "go for a run", "later", 2) is not None

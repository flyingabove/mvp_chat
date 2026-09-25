"""Step 4: engine-chosen speakers and initiative."""
from backend.app.engine.world_model.speakers import addressed_ids, select_speakers
from backend.app.engine.world_model.threads import Milestone, Thread
from tests.backend.app.engine.world_model.helpers import make_model


def _model():
    model = make_model({"uchi": "kitchen", "arisa": "kitchen", "hikaru": "kitchen", "yuto": "living_room"})
    model.characters["uchi"].name = 'Tatsuya "Uchi" Uchihara'
    model.characters["arisa"].name = "Arisa Ohata"
    model.characters["hikaru"].name = "Hikaru Ota"
    return model


def test_nickname_and_first_name_address_detection():
    model = _model()
    addressed, mentioned = addressed_ids(model, "Hey Uchi, where's the salon?", ["uchi", "arisa"])
    assert addressed == {"uchi"} and mentioned == {"uchi"}
    addressed, mentioned = addressed_ids(model, "I heard Arisa makes hats.", ["uchi", "arisa"])
    assert addressed == set() and mentioned == {"arisa"}
    addressed, _ = addressed_ids(model, "I turn to Hikaru and ask about work", ["hikaru"])
    assert addressed == {"hikaru"}


def test_the_addressed_person_is_primary():
    model = _model()
    plan = select_speakers(model, ["uchi", "arisa", "hikaru"], "Arisa, what do you design?")
    assert plan.primary == "arisa" and plan.reason == "addressed"
    assert len(plan.speakers) <= 2


def test_group_address_brings_in_up_to_three_speakers():
    model = _model()
    plan = select_speakers(model, ["uchi", "arisa", "hikaru"], "hey everyone, what's for dinner?")
    assert 2 <= len(plan.speakers) <= 3 and plan.reason == "group address"
    assert set(plan.silent_present) | set(plan.speakers) == {"uchi", "arisa", "hikaru"}


def test_recency_rotation_prevents_one_character_dominating():
    model = _model()
    primaries = []
    for turn in range(1, 9):
        model.turn = turn
        plan = select_speakers(model, ["uchi", "arisa", "hikaru"], "this is nice")
        primaries.append(plan.primary)
        for cid in plan.speakers:
            model.characters[cid].record_spoke(turn)
    assert len(set(primaries)) == 3
    assert max(primaries.count(c) for c in set(primaries)) <= 4


def test_absent_or_asleep_people_are_never_chosen():
    model = _model()
    model.characters["hikaru"].availability = "asleep"
    plan = select_speakers(model, ["uchi", "arisa", "hikaru", "ghost"], "Hikaru, are you awake?")
    assert "hikaru" not in plan.speakers and "ghost" not in plan.speakers
    assert select_speakers(model, [], "hello").speakers == []


def test_thread_topics_and_warmth_raise_a_speaker():
    model = _model()
    model.threads.append(Thread("t", "hikaru", "work", topics=["construction"],
                                milestones=[Milestone("m", 5, "10:00", "x")]))
    plan = select_speakers(model, ["uchi", "arisa", "hikaru"], "any construction work lately?")
    assert plan.primary == "hikaru"
    warm = select_speakers(model, ["uchi", "arisa"], "nice evening",
                           warmth=lambda cid: 1.0 if cid == "uchi" else -1.0)
    assert warm.primary == "uchi"


def test_selection_is_deterministic_for_the_same_turn():
    a, b = _model(), _model()
    assert select_speakers(a, ["uchi", "arisa", "hikaru"], "so").speakers == \
        select_speakers(b, ["uchi", "arisa", "hikaru"], "so").speakers

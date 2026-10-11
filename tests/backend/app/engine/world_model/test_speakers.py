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


# ---------------------------------------------------------------- BL-101: the speaker's own stances
def _score_order(model, message, who=("uchi", "arisa", "hikaru")):
    plan = select_speakers(model, list(who), message)
    return plan, [plan.primary, *plan.secondary]


def _stance(model, kind, holder, target, about="", strength=1.0):
    from backend.app.engine.world_model.stances import Stance
    model.stances.add(Stance(kind, holder, target, strength, about, (), 0))


def test_a_protective_person_speaks_up_when_the_one_they_protect_is_mentioned():
    model = _model()
    _stance(model, "protective_of", "hikaru", "arisa")
    plan, order = _score_order(model, "I think Arisa makes odd hats.")
    assert "hikaru" in order and "uchi" not in order, order
    baseline, _ = _score_order(_model(), "I think Arisa makes odd hats.")
    assert "hikaru" not in baseline.speakers, "without the stance hikaru stays quiet"


def test_a_rival_cuts_in_when_the_person_they_both_want_is_addressed():
    model = _model()
    _stance(model, "rival", "hikaru", "uchi", about="arisa")
    plan, order = _score_order(model, "Arisa, what do you design?")
    assert plan.primary == "arisa" and "hikaru" in plan.secondary


def test_stance_pull_is_capped_below_being_addressed_and_ignores_other_kinds():
    from backend.app.engine.world_model.speakers import STANCE_CAP, stance_pull
    model = _model()
    for kind in ("protective_of", "resents", "crush", "rival"):
        _stance(model, kind, "hikaru", "arisa", about="arisa")
    assert stance_pull(model, "hikaru", {"arisa"}) == STANCE_CAP < 5.0
    _stance(model, "suspects", "uchi", "arisa")
    assert stance_pull(model, "uchi", {"arisa"}) == 0.0
    assert stance_pull(model, "hikaru", {"uchi"}) == 0.0


def test_someone_who_distrusts_the_player_does_not_volunteer_but_still_answers_when_addressed():
    model = _model()
    _stance(model, "distrusts", "arisa", "player")
    model.characters["arisa"].last_spoke_turn = -10
    quiet = select_speakers(model, ["arisa", "hikaru"], "Hello everyone.")
    assert quiet.primary == "hikaru"
    assert select_speakers(model, ["arisa", "hikaru"], "Arisa, hello.").primary == "arisa"

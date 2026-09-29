from backend.app.engine.world_model.conversation import (
    LAPSE_AFTER_TURNS, MAX_OPEN, ConversationState,
)


def test_questions_stay_open_until_a_real_resolution():
    convo = ConversationState()
    a = convo.ask("iu", "Who told you about the footage?", turn=1)
    b = convo.ask("iu", "Did you check the camera?", turn=1)
    assert [q.id for q in convo.open_questions()] == [a.id, b.id]

    assert not convo.resolve(a.id, "unanswered", turn=2)
    assert convo.resolve(a.id, "refused", turn=2)
    assert [q.id for q in convo.open_questions()] == [b.id]
    assert not convo.resolve(a.id, "answered", turn=3), "a closed question cannot be resolved twice"


def test_each_resolution_kind_closes_the_question():
    for status in ("answered", "refused", "unknown", "deferred"):
        convo = ConversationState()
        q = convo.ask("mako", "Are you free tonight?", turn=1)
        assert convo.resolve(q.id, status, turn=2)
        assert convo.open_questions() == []


def test_repeating_an_open_question_does_not_duplicate_it():
    convo = ConversationState()
    first = convo.ask("iu", "Where were you at 8?", turn=1)
    again = convo.ask("iu", "where were you  at 8?", turn=2)
    assert again is first
    assert len(convo.open_questions()) == 1


def test_stale_questions_lapse_and_history_is_bounded():
    convo = ConversationState()
    old = convo.ask("iu", "Old question?", turn=1)
    fresh = convo.ask("iu", "Fresh question?", turn=LAPSE_AFTER_TURNS)
    convo.lapse_stale(turn=LAPSE_AFTER_TURNS + 1)
    assert old.status == "lapsed"
    assert [q.id for q in convo.open_questions()] == [fresh.id]


def test_open_questions_are_capped_by_lapsing_the_oldest():
    convo = ConversationState()
    asked = [convo.ask("iu", f"Question {i}?", turn=1) for i in range(MAX_OPEN + 2)]
    open_ids = [q.id for q in convo.open_questions()]
    assert open_ids == [q.id for q in asked[-MAX_OPEN:]]
    assert asked[0].status == "lapsed"


def test_blank_input_is_ignored_and_state_round_trips():
    convo = ConversationState()
    assert convo.ask("", "Hello?", 1) is None
    assert convo.ask("iu", "   ", 1) is None
    q = convo.ask("iu", "Hello?", 1)
    convo.resolve(q.id, "answered", 2)
    convo.ask("mako", "And you?", 2)
    restored = ConversationState.from_dict(convo.to_dict())
    assert restored.to_dict() == convo.to_dict()
    assert restored.ask("mako", "New?", 3).id == "q3"

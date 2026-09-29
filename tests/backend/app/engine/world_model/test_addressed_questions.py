"""BL-39 O08: questions the player addresses to a character stay owed until resolved."""
from types import SimpleNamespace

from backend.app.engine.extractors.turn_extractor import QuestionAsked, QuestionStatusUpdate
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.turn import begin_turn, record_questions

from tests.backend.app.engine.world_model.helpers import make_model


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul",
                           story_cfg={"world_model": {"enabled": True}},
                           characters=model.characters, cast_lifecycle=None, character_graph=None)


def _question_lines(model):
    return [line for line in model.view.must_address if "The player asked" in line]


def test_two_questions_to_one_character_both_reach_the_scene_contract():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    message = "Ann, where were you at 8? And who told you about the footage?"
    record_questions(state, [QuestionAsked("ann", "Where were you at 8?"),
                             QuestionAsked("ann", "Who told you about the footage?")], [], message=message)
    view = begin_turn(state, message, 0)
    lines = _question_lines(model)
    assert len(lines) == 2
    assert all("Ann must respond to it directly" in line for line in lines)
    assert "ann" in view.plan.speakers


def test_answering_one_question_leaves_the_other_owed_next_turn():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    message = "Ann, where were you at 8? Who told you?"
    record_questions(state, [QuestionAsked("ann", "Where were you at 8?"),
                             QuestionAsked("ann", "Who told you?")], [], message=message)
    begin_turn(state, message, 0)
    first, second = model.conversation.open_questions()

    record_questions(state, [], [QuestionStatusUpdate(first.id, "answered"),
                                 QuestionStatusUpdate(second.id, "unanswered")], message="Hmm.")
    view = begin_turn(state, "Hmm.", 0)
    lines = _question_lines(model)
    assert len(lines) == 1
    assert '"Who told you?"' in lines[0] and "still unanswered" in lines[0]
    assert view.plan.primary == "ann", "the character who owes an answer is chosen to speak"


def test_a_question_to_an_absent_character_is_not_reassigned():
    model = make_model({"ann": "kitchen", "cat": "garden"})
    state = _state(model)
    record_questions(state, [QuestionAsked("cat", "Did you lock the door?")], [],
                     message="Cat, did you lock the door?")
    view = begin_turn(state, "Cat, did you lock the door?", 0)
    lines = _question_lines(model)
    assert lines == ['The player asked Cat, who is not here: "Did you lock the door?". Nobody else answers '
                     "for Cat; someone present may say Cat is not here."]
    assert "cat" not in view.plan.speakers

    begin_turn(state, "Anyway.", 0)
    assert _question_lines(model) == [], "an absent addressee is not re-announced every turn"
    assert [q.addressee for q in model.conversation.open_questions()] == ["cat"]


def test_an_owed_question_resurfaces_when_the_addressee_arrives():
    model = make_model({"ann": "kitchen", "cat": "garden"})
    state = _state(model)
    record_questions(state, [QuestionAsked("cat", "Did you lock the door?")], [],
                     message="Cat, did you lock the door?")
    begin_turn(state, "Cat, did you lock the door?", 0)
    model.world.move("cat", "kitchen")
    begin_turn(state, "Oh, you're back.", 0)
    assert any("Cat must respond" in line for line in _question_lines(model))


def test_a_question_not_in_the_current_message_is_not_recorded():
    """Live regression (2026-09-28): after Riko answered, the player said
    "Hmm, okay." and the extractor re-reported the previous turn's question,
    so the storyteller made her answer it all over again."""
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("ann", "What do you do for work?")], [], message="Hmm, okay.")
    assert model.conversation.open_questions() == []


def test_questions_grounded_in_the_message_are_recorded_even_when_paraphrased_lightly():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("ann", "What do you do for work?"),
                             QuestionAsked("ann", "你住哪里")], [],
                     message="Ann, so what do you do for work these days? 你住哪里？")
    assert [q.text for q in model.conversation.open_questions()] == ["What do you do for work?",
                                                                      "你住哪里"]


def test_unknown_addressees_and_resolutions_are_ignored():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("nobody", "Hello?")], [QuestionStatusUpdate("q99", "answered")],
                     message="Hello?")
    assert model.conversation.open_questions() == []


def test_open_questions_survive_a_save_round_trip():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("ann", "Where were you?")], [], message="Ann, where were you?")
    begin_turn(state, "Ann, where were you?", 0)
    restored = WorldModel.from_dict(model.to_dict())
    assert [(q.addressee, q.text) for q in restored.conversation.open_questions()] == [("ann", "Where were you?")]


def test_a_question_the_addressee_keeps_answering_is_closed_by_the_engine():
    """Live beta 2026-09-29: the extractor never marked it answered and Riko re-answered it ~8 turns."""
    from backend.app.engine.world_model.conversation import MAX_DIRECTED_REPLIES
    from backend.app.engine.world_model.turn import end_turn

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("ann", "How are you finding this place?")], [],
                     message="How are you finding this place?")
    reply = [{"kind": "dialogue", "speaker_id": "ann", "text": "Strange."},
             {"kind": "dialogue", "speaker_id": "ann", "text": "But it has potential."}]
    for _ in range(MAX_DIRECTED_REPLIES):
        assert model.conversation.open_questions(), "still owed until she has replied enough"
        begin_turn(state, "Hmm.", 0)
        end_turn(state, "Hmm.", reply)      # two lines in one turn count as one reply
    assert model.conversation.open_questions() == []
    begin_turn(state, "Anyway.", 0)
    assert _question_lines(model) == []


def test_other_peoples_chatter_does_not_count_as_the_addressees_reply():
    from backend.app.engine.world_model.turn import end_turn

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("ann", "Where were you?")], [], message="Where were you?")
    for _ in range(4):
        begin_turn(state, "Well?", 0)
        end_turn(state, "Well?", [{"kind": "dialogue", "speaker_id": "ben", "text": "Nice weather."}])
    assert [q.addressee for q in model.conversation.open_questions()] == ["ann"]


def test_reply_count_survives_a_save_round_trip():
    from backend.app.engine.world_model.conversation import ConversationState

    convo = ConversationState()
    convo.ask("ann", "Where were you?", 1)
    convo.note_reply("ann", 1)
    assert ConversationState.from_dict(convo.to_dict()).questions[0].replies == 1

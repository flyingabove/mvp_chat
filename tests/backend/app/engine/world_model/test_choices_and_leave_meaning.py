"""BL-46: the in-chat choice card and the "what did leave together mean" question."""
import asyncio
from types import SimpleNamespace

from backend.app.api.user_sessions import _saved_choice
from backend.app.engine.world_model import choices, leave_meaning
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.social_acts import CONFIRMED, SocialAct, Verdict, directive
from backend.app.engine.world_model.turn import answer_choice, apply_leave_meaning, leave_meaning_subject
from backend.app.llm.decisions.types import Provider

from tests.backend.app.engine.world_model.helpers import make_model

ASK = SimpleNamespace(kind="ask_leave_together", target="ann")


def _couple_model():
    model = make_model({"ann": "kitchen"})
    model.romance_relationship_partner = "ann"
    return model


def _state(model):
    cfg = {"world_model": {"enabled": True}}
    return SimpleNamespace(world_model=model, story_cfg=cfg, minute=0)


def test_offering_records_a_persisted_card_the_player_can_answer():
    model = _couple_model()
    card = choices.offer_leave_together(model, "ann")
    assert card["partner"] == "ann" and [o["id"] for o in card["options"]] == ["leave_now", "keep_talking"]
    assert choices.payload(model) == {"id": "leave_together", "kind": "leave_together", "prompt": card["prompt"],
                                      "chip": "Play ending", "options": card["options"]}
    assert "partner" not in choices.payload(model), "no internal fields reach the player"
    saved = WorldModel.from_dict(model.to_dict())
    assert saved.pending_choice == model.pending_choice, "survives a save and reload"
    assert choices.answer(model, "__choice__:leave_together:leave_now") == "leave_now"
    assert choices.answer(model, "__choice__:leave_together:keep_talking") == "keep_talking"
    assert choices.answer(model, "__choice__:leave_together:nonsense") is None
    for text in ("[play ending]", "(Play the ending)", "[play credits]"):
        assert choices.answer(model, text) == "leave_now", text
    assert choices.answer(model, "I want to play the ending of this story") is None


def test_the_yes_lapses_at_day_end_or_when_the_relationship_ends():
    model = _couple_model()
    choices.offer_leave_together(model, "ann")
    assert choices.refresh(model) is None and model.pending_choice, "still valid the same day"
    model.world.minute += 24 * 60
    note = choices.refresh(model)
    assert model.pending_choice == {} and "no longer stands" in note

    model = _couple_model()
    choices.offer_leave_together(model, "ann")
    model.romance_relationship_partner = ""
    assert "no longer stands" in choices.refresh(model) and model.pending_choice == {}


def test_leave_now_queues_the_confirmed_departure_and_the_finale_directive():
    model = _couple_model()
    state = _state(model)
    choices.offer_leave_together(model, "ann")
    cue = answer_choice(state, "__choice__:leave_together:leave_now")
    assert "leave the house together with Ann now" in cue
    [verdict] = model.pending_verdicts
    assert verdict.act == SocialAct("ask_leave_together", "ann") and verdict.hint == CONFIRMED
    assert "leave the house together for good" in directive(verdict, model.names())


def test_leave_now_needs_the_partner_in_the_room():
    model = _couple_model()
    state = _state(model)
    choices.offer_leave_together(model, "ann")
    model.world.move("ann", "garden")
    cue = answer_choice(state, "[play ending]")
    assert "is not here" in cue and model.pending_verdicts == []
    assert any("find them first" in note for note in model.pending_notes)
    assert model.pending_choice, "the yes still stands until it lapses"


def test_keep_talking_and_stale_answers_continue_the_scene():
    model = _couple_model()
    state = _state(model)
    choices.offer_leave_together(model, "ann")
    assert "keep talking" in answer_choice(state, "__choice__:leave_together:keep_talking")
    assert model.pending_verdicts == [] and model.pending_choice
    model.pending_choice = {}
    assert "no longer stands" in answer_choice(state, "__choice__:leave_together:leave_now")
    assert model.pending_verdicts == []
    assert answer_choice(state, "[play ending]") is None, "with no card it is an ordinary game-master message"
    assert answer_choice(state, "Hello there") is None


def test_saved_card_is_returned_for_resume_but_not_after_the_ending():
    import json
    model = _couple_model()
    choices.offer_leave_together(model, "ann")
    state_json = json.dumps({"world_model": model.to_dict()})
    assert _saved_choice(state_json)["id"] == "leave_together"
    assert _saved_choice(json.dumps({"world_model": model.to_dict(), "outcome": {"ending_id": "x"}})) is None
    assert _saved_choice(None) is None and _saved_choice("not json") is None


def test_decline_directive_names_the_room_so_narration_stays_put():
    verdict = Verdict(SocialAct("ask_leave_together", "ann"), "not_yet", "you are not together yet")
    text = directive(verdict, {"ann": "Ann"}, place="the living room")
    assert "The scene stays at the living room; nobody leaves unless the player says so." in text
    assert "The scene stays" not in directive(verdict, {"ann": "Ann"}), "no place, no claim"


def test_only_an_ask_to_leave_together_needs_its_meaning_read():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    assert leave_meaning_subject(state, SimpleNamespace(kind="confess", target="ann")) is None
    assert leave_meaning_subject(state, ASK) == ("ann", "Ann", False)
    model.romance_relationship_partner = "ann"
    assert leave_meaning_subject(state, ASK) == ("ann", "Ann", True)


def test_an_outing_or_unclear_ask_is_not_a_typed_act_and_queues_the_right_note():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    assert apply_leave_meaning(state, ASK, "couple") is ASK
    assert apply_leave_meaning(state, ASK, "outing") is None
    assert "not to leave the house for good" in model.pending_notes[-1]
    assert apply_leave_meaning(state, ASK, "unclear") is None
    assert "asks which they mean" in model.pending_notes[-1]
    assert model.pending_verdicts == [] and model.act_cooldowns == {}


class _Resolver:
    def __init__(self, choice=None, usable=True, provider=Provider.JEV, boom=False):
        self.answer = SimpleNamespace(choice=choice, usable=usable, provider=provider)
        self.boom = boom
        self.seen = []

    async def resolve(self, batches, request):
        self.seen.append(batches[0].state)
        if self.boom:
            raise RuntimeError("down")
        return SimpleNamespace(answers={leave_meaning.TASK: self.answer})


def _classify(couple, resolver):
    return asyncio.run(leave_meaning.classify("Ann, leave with me?", "Ann", couple, resolver))


def test_jev_answer_is_used_and_sees_the_relationship_status():
    resolver = _Resolver("outing")
    assert _classify(False, resolver) == "outing"
    assert "not a couple yet" in resolver.seen[0] and "Ann, leave with me?" in resolver.seen[0]
    assert _classify(True, _Resolver("couple")) == "couple"
    couple_resolver = _Resolver("unclear")
    assert _classify(True, couple_resolver) == "unclear"
    assert "already a romantic couple" in couple_resolver.seen[0]


def test_without_a_usable_jev_answer_a_couple_means_the_win_and_others_are_asked():
    for resolver in (_Resolver(None, usable=False), _Resolver("outing", provider=Provider.LEGACY_LLM),
                     _Resolver("bogus"), _Resolver(boom=True)):
        assert _classify(True, resolver) == "couple"
        assert _classify(False, resolver) == "unclear"

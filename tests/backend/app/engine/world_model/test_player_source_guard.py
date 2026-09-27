"""A model cannot invent a player's prior testimony as an NPC source."""
from tests.backend.app.engine.world_model.helpers import make_model
from backend.app.engine.world_model.epistemics import observe_event
from backend.app.engine.world_model.model import PLAYER


def heard_player(model, listener: str, text: str) -> None:
    event = model.world.add_event(model.world.minute, model.player_place(), (PLAYER, listener),
                                  f"@{PLAYER} said: {text}", kind="utterance",
                                  payload={"speaker": PLAYER, "text": text})
    observe_event(model.epistemics, listener, event.id, "heard", event.truth, model.world.minute)


def test_question_about_missing_items_does_not_authorize_false_player_attribution():
    from backend.app.engine.world_model.source_guard import ground_player_attribution

    model = make_model({"ann": "kitchen"})
    model.player_name = "Mira"
    heard_player(model, "ann", "What items went missing?")
    reply = "Mira asked me about it. She said there were other things that went missing too."
    assert ground_player_attribution(model, "ann", reply) == (
        "Mira asked me about it. I may be mixing up who told me that."
    )
    assert ground_player_attribution(model, "ann", "I remember Mira mentioned other missing items to me.") == (
        "I may be mixing up who told me that."
    )


def test_actual_witnessed_player_statement_can_be_attributed():
    from backend.app.engine.world_model.source_guard import ground_player_attribution

    model = make_model({"ann": "kitchen"})
    model.player_name = "Mira"
    heard_player(model, "ann", "I found a phone and notebook in the closet.")
    reply = "Mira told me she found a phone and notebook in the closet."
    assert ground_player_attribution(model, "ann", reply) == reply


def test_absent_npc_cannot_claim_to_have_heard_player_statement():
    from backend.app.engine.world_model.source_guard import ground_player_attribution

    model = make_model({"ann": "kitchen", "ben": "outside"})
    model.player_name = "Mira"
    heard_player(model, "ann", "I found a phone and notebook in the closet.")
    assert ground_player_attribution(
        model, "ben", "Mira told me she found a phone and notebook in the closet."
    ) == "I may be mixing up who told me that."


def test_generated_iu_dialogue_is_checked_before_reaching_player():
    from types import SimpleNamespace
    from backend.app.engine.dialogue import ground_social_scene

    model = make_model({"ann": "kitchen"})
    model.player_name = "Mira"
    heard_player(model, "ann", "What items went missing?")
    state = SimpleNamespace(world_model=model, minute=0, location="Kitchen",
                            world_start_datetime="2025-01-01T20:00:00", story_cfg={"mode": {}})
    segments = [{"kind": "dialogue", "speaker_id": "ann", "text":
                 "Mira asked me about it. She said there were other things that went missing too."}]
    result = ground_social_scene(segments, state)
    assert result == [{"kind": "dialogue", "speaker_id": "ann", "text":
                       "Mira asked me about it. I may be mixing up who told me that."}]


def test_heard_player_mention_claim_requires_witnessed_statement():
    from backend.app.engine.world_model.source_guard import ground_player_attribution

    model = make_model({"ann": "kitchen"})
    model.player_name = "Mira"
    heard_player(model, "ann", "Is there a dated record or witness I can consult?")
    assert ground_player_attribution(
        model, "ann", "I heard Mira mention checking the building's security footage."
    ) == "I may be mixing up who told me that."

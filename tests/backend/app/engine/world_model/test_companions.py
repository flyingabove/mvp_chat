"""Live beta bug 2026-09-29: an invited housemate must travel with the player, and only then."""
from types import SimpleNamespace

from backend.app.engine.world_model.companions import choose_companions
from backend.app.engine.world_model.model import PLAYER
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model


def _state(model, location_id):
    return SimpleNamespace(world_model=model, minute=0, location_id=location_id, player_name="Paul",
                           story_cfg={"world_model": {"enabled": True}}, characters=model.characters,
                           cast_lifecycle=None, character_graph=None)


def test_named_invitee_travels_with_the_player():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    assert choose_companions(model, "Ann, come with me to the cafe.", ["ann", "ben"]) == ["ann"]


def test_begin_turn_moves_the_companion_and_leaves_the_rest():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model, "cafe")
    begin_turn(state, "Ann, it's time for our coffee. Come with me to the cafe - I'll walk you there.", 0)
    assert model.world.place_of(PLAYER) == "cafe"
    assert model.world.place_of("ann") == "cafe"
    assert model.world.place_of("ben") == "kitchen"
    assert model.present_with_player() == ["ann"]
    assert state.character_locations["ann"] == "cafe"


def test_lone_resident_comes_along_without_being_named():
    model = make_model({"ann": "kitchen"})
    assert choose_companions(model, "Let's go to the cafe together.", ["ann"]) == ["ann"]


def test_unnamed_invitation_with_a_crowd_takes_nobody():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    assert choose_companions(model, "Let's go to the cafe.", ["ann", "ben"]) == []


def test_plain_move_takes_nobody():
    model = make_model({"ann": "kitchen"})
    state = _state(model, "garden")
    begin_turn(state, "I go to the garden.", 0)
    assert model.world.place_of("ann") == "kitchen"


def test_future_or_conditional_invitation_is_not_a_move():
    model = make_model({"ann": "kitchen"})
    for text in ("I go to the garden and ask Ann if she wants to come with me later.",
                 "Tomorrow, come with me to the cafe, Ann."):
        assert choose_companions(model, text, ["ann"]) == []


def test_sleeping_or_cold_residents_stay():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    model.characters["ann"].availability = "asleep"
    assert choose_companions(model, "Ann, come with me to the cafe.", ["ann"]) == []
    assert choose_companions(model, "Ben, come with me to the cafe.", ["ben"],
                             warmth=lambda cid: -0.4) == []


def test_only_residents_in_the_room_can_be_invited():
    model = make_model({"ann": "garden", "ben": "kitchen"})
    assert choose_companions(model, "Ann, come with me to the cafe.", ["ben"]) == []

"""BL-34: same-gender housemates compete visibly for the person the player is winning.

Causes fixed: the player was never counted as an admirer (so a rival never competed with the player), rivals had
no aim of their own in the first days, and a compete_for intention gave no visible beat.
"""
import copy
from types import SimpleNamespace

import pytest

from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.agenda import SocialContext, intentions, next_beat
from tests.backend.app.engine.world_model.test_agenda import refresh_all
from backend.app.engine.world_model.rivals import seed_rival_aims
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import BEAT_TEXT, begin_turn

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]
RULES = social_rules(TERRACE)
TRACK, INTERESTED = RULES.appraisal.track, RULES.couples.interested_tier
GENDERS = {"ben": "M", "dan": "M", "ann": "F", "cat": "F", "eve": "F", "player": "M"}


def _model(people=None):
    model = make_model(people or {"ben": "kitchen", "dan": "kitchen", "ann": "kitchen", "cat": "kitchen"})
    model.standing.bind(RULES.tracks)
    for cid in model.characters:                 # residents who have lived with the player a while (past strangers)
        model.first_met_day[cid], model.turns_together[cid] = 0, 30
    return model


def _set(model, owner, target, value, closed_by=""):
    model.standing.standings[(owner, target, TRACK)] = Standing(value=value, closed_by=closed_by)


def _refresh(model, genders=None, day=0):
    ctx = SocialContext(RULES, dict(genders or GENDERS))
    refresh_all(model, ctx, day)


def _kinds(model, cid, day=0):
    return {(i.kind, i.target) for i in intentions(model, cid, day)}


def test_a_target_the_player_is_winning_makes_a_drawn_rival_compete_for_her():
    model = _model()
    _set(model, "ann", "player", 50)       # Ann has warmed to the player (interested tier)
    _set(model, "ben", "ann", 48)          # Ben is drawn to Ann too
    _refresh(model)
    assert ("compete_for", "ann") in _kinds(model, "ben"), "today he only 'pursues' and nothing shows"
    assert "player" not in model.agendas, "the player never gets an agenda"


def test_no_second_admirer_means_no_competition():
    model = _model()
    _set(model, "ben", "ann", 48)          # Ben likes Ann; the player has not won her
    _refresh(model)
    assert _kinds(model, "ben") == {("pursue", "ann")}
    model = _model()
    _set(model, "ann", "player", 50)       # the player is winning Ann; nobody else is drawn to her
    _refresh(model)
    assert not any(_kinds(model, cid) for cid in ("ben", "dan"))


def test_two_rivals_on_one_target_both_compete():
    model = _model()
    _set(model, "ann", "player", 50)
    _set(model, "ben", "ann", 48)
    _set(model, "dan", "ann", 47)
    _refresh(model)
    assert ("compete_for", "ann") in _kinds(model, "ben") and ("compete_for", "ann") in _kinds(model, "dan")


def test_a_taken_or_rejecting_target_is_not_competed_for():
    taken = _model()
    _set(taken, "ann", "player", 50)
    _set(taken, "ben", "ann", 48)
    taken.npc_couples["ann|cat"] = 0                     # Ann is already in a couple with someone else
    _refresh(taken)
    assert ("compete_for", "ann") not in _kinds(taken, "ben")

    rejecting = _model()
    _set(rejecting, "ann", "player", 50, closed_by="dealbreaker")   # she has closed the door on the player
    _set(rejecting, "ben", "ann", 48)
    _refresh(rejecting)
    assert _kinds(rejecting, "ben") == {("pursue", "ann")}, "the player is not a rival for someone who said no"


@pytest.mark.parametrize("player_gender, rival, target", [("M", "ben", "ann"), ("F", "ann", "ben")])
def test_it_works_for_both_player_genders(player_gender, rival, target):
    genders = {**GENDERS, "player": player_gender}
    model = _model()
    _set(model, target, "player", 50)
    _set(model, rival, target, 48)
    _refresh(model, genders)
    assert ("compete_for", target) in _kinds(model, rival)


def test_a_departed_rival_leaves_no_intention_behind():
    model = _model({"dan": "kitchen", "ann": "kitchen"})          # Ben rotated out of the house
    _set(model, "ann", "player", 50)
    _set(model, "ben", "ann", 48)
    _refresh(model)
    assert "ben" not in model.agendas and not _kinds(model, "dan")


def test_a_present_rival_gets_a_visible_beat_naming_who_he_is_after():
    model = _model()
    _set(model, "ann", "player", 50)
    _set(model, "ben", "ann", 48)
    _refresh(model)
    cid, intention = next_beat(model, {"ben", "ann"}, 0)
    assert (cid, intention.kind, intention.target) == ("ben", "compete_for", "ann")
    assert next_beat(model, {"ben"}, 0) is None, "no beat when the target is not in the scene"
    text = BEAT_TEXT["compete_for"].format(name="Ben", target="Ann")
    assert "Ben" in text and "Ann" in text and "ONE small" in text and "does not confess" in text


def test_the_beat_reaches_the_storyteller_through_a_real_turn():
    """Real Terrace ids (the story gives them genders): Makoto is drawn to Minori, whom the player is winning."""
    model = _model({"makoto": "kitchen", "minori": "kitchen"})
    _set(model, "minori", "player", 50)
    _set(model, "makoto", "minori", 48)
    state = SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=TERRACE,
                            characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                            cast_lifecycle=None, character_graph=None, gender="M", turns=5, outcome=None)
    view = begin_turn(state, "Morning, everyone.", 0)
    assert any("Makoto" in line and "Minori" in line and "drawn to" in line for line in view.must_address),         view.must_address


def _seed_cfg(value):
    cfg = copy.deepcopy(TERRACE)
    if value is None:
        cfg["social_tracks"]["couples"].pop("rival_aim", None)
    else:
        cfg["social_tracks"]["couples"]["rival_aim"] = value
    return cfg


FIVE = {"ben": "kitchen", "dan": "kitchen", "ann": "kitchen", "cat": "kitchen", "eve": "kitchen"}


@pytest.mark.parametrize("player_gender", ["M", "F"])
def test_every_rival_gets_an_aim_of_their_own_on_day_zero(player_gender):
    model = _model(FIVE)
    genders = {**GENDERS, "player": player_gender}
    pairs = seed_rival_aims(model, social_rules(_seed_cfg(0.3)), genders, player_gender)
    rivals = {cid for cid, g in genders.items() if g == player_gender and cid in model.characters}
    assert {rival for rival, _ in pairs} == rivals
    for rival, crush in pairs:
        assert genders[crush] != player_gender and crush in model.characters
        assert ("pursue", crush) in _kinds(model, rival), "the aim exists before anyone has met"
    _refresh(model, genders, day=30)                      # long after: the aim outlives the short intention window
    for rival, crush in pairs:
        assert ("pursue", crush) in _kinds(model, rival, day=30)


def test_an_aim_that_overlaps_the_players_choice_turns_into_competition():
    model = _model(FIVE)
    (rival, crush), *_ = seed_rival_aims(model, social_rules(_seed_cfg(0.3)), GENDERS, "M")
    _set(model, crush, "player", 50)                      # the player wins that same person
    _refresh(model)
    assert ("compete_for", crush) in _kinds(model, rival)


def test_seeding_is_deterministic_opt_in_and_never_duplicates():
    first, second = _model(FIVE), _model(FIVE)
    a = seed_rival_aims(first, social_rules(_seed_cfg(0.3)), GENDERS, "M")
    b = seed_rival_aims(second, social_rules(_seed_cfg(0.3)), GENDERS, "M")
    assert a == b, "same house, same aims"
    assert seed_rival_aims(_model(FIVE), social_rules(_seed_cfg(None)), GENDERS, "M") == [], "off unless the story opts in"
    again = seed_rival_aims(first, social_rules(_seed_cfg(0.3)), GENDERS, "M")
    assert again == [] and all(len(model_items) == 1 for model_items in first.agendas.values())


def test_a_rival_who_is_already_coupled_gets_no_new_aim():
    model = _model(FIVE)
    model.npc_couples["ben|ann"] = 0
    pairs = dict(seed_rival_aims(model, social_rules(_seed_cfg(0.3)), GENDERS, "M"))
    assert "ben" not in pairs and "dan" in pairs


def test_rival_aim_is_validated_in_the_story_rules():
    assert social_rules(_seed_cfg(0.3)).couples.rival_aim == 0.3
    assert social_rules(_seed_cfg(None)).couples.rival_aim == 0
    for bad in (-0.1, 1.5, "lots"):
        with pytest.raises(ValueError):
            social_rules(_seed_cfg(bad))


# --- second pass: residents who arrive later, and aims whose target is gone ---------------------------------------

def _terrace_genders(player_gender="M"):
    genders = {c["key"]: c["gender"] for c in TERRACE["characters"]}
    genders["player"] = player_gender
    return genders


def _arrival_state(keys, gender="M"):
    return SimpleNamespace(story_cfg=TERRACE, gender=gender, cast_lifecycle=None, character_locations={},
                           characters={k: SimpleNamespace(name=k.title(), role="Housemate", tells=[]) for k in keys})


def test_a_resident_who_arrives_later_gets_an_aim_through_sync_membership():
    from backend.app.engine.world_model.bootstrap import seed_rival_aims_for_state
    from backend.app.engine.world_model.turn import sync_membership
    model = _model({"makoto": "kitchen", "minori": "kitchen", "mizuki": "kitchen"})
    state = _arrival_state(["makoto", "minori", "mizuki", "uchi"])         # Uchi (M) moves in after the start
    seed_rival_aims_for_state(_arrival_state(["makoto", "minori", "mizuki"]), model)
    before = {cid: _kinds(model, cid) for cid in model.characters}
    sync_membership(model, state)
    assert "uchi" in model.characters
    assert any(kind == "pursue" for kind, _ in _kinds(model, "uchi")), "the newcomer has an aim of their own"
    assert all(_kinds(model, cid) == before[cid] for cid in before), "existing aims are untouched"
    sync_membership(model, state)
    assert len([i for i in model.agendas["uchi"] if i.kind == "pursue"]) == 1, "idempotent"


def test_an_arrival_of_the_other_gender_gets_no_aim():
    from backend.app.engine.world_model.turn import sync_membership
    model = _model({"makoto": "kitchen", "minori": "kitchen"})
    sync_membership(model, _arrival_state(["makoto", "minori", "mizuki"]))
    assert "mizuki" in model.characters and "mizuki" not in model.agendas, "she is not a rival for a male player"


def test_a_rival_whose_target_left_or_coupled_is_given_a_new_aim():
    model = _model({"makoto": "kitchen", "minori": "kitchen", "mizuki": "kitchen", "yuriko": "kitchen"})
    genders = _terrace_genders()
    rules = social_rules(_seed_cfg(0.3))
    (first_rival, first_target), = seed_rival_aims(model, rules, genders, "M")
    assert first_rival == "makoto"
    model.npc_couples[f"{first_target}|yuriko" if first_target != "yuriko" else "yuriko|minori"] = 0   # target taken
    again = dict(seed_rival_aims(model, rules, genders, "M"))
    assert again.get("makoto") and again["makoto"] != first_target, "re-aimed at someone still free"
    gone = _model({"makoto": "kitchen", "minori": "kitchen", "mizuki": "kitchen"})
    (r, t), = seed_rival_aims(gone, rules, genders, "M")
    gone.characters.pop(t)                                                    # the target moved out
    assert dict(seed_rival_aims(gone, rules, genders, "M")).get(r) not in (None, t)


# --- beat safety ----------------------------------------------------------------------------------------------------

def _terrace_state(model, gender="M"):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=TERRACE,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender=gender, turns=5, outcome=None)


def _compete_lines(view):
    return [line for line in view.must_address if "ONE small" in line]


def test_the_rival_beat_claims_no_feelings_and_invents_no_thoughts():
    text = BEAT_TEXT["compete_for"].format(name="Makoto", target="Minori")
    for claim in ("in love", "loves", "secretly", "jealous", "hates", "wants her", "wants him"):
        assert claim not in text.lower(), claim
    assert "does not confess" in text and "privately feel" in text, "the prohibition is spelled out"


def test_a_rival_makes_at_most_one_visible_move_per_day_and_the_replay_rate_is_bounded():
    model = _model({"makoto": "kitchen", "uchi": "kitchen", "minori": "kitchen"})
    _set(model, "minori", "player", 50)
    _set(model, "makoto", "minori", 48)
    _set(model, "uchi", "minori", 47)
    state = _terrace_state(model)
    beats = 0
    for turn in range(25):                       # one long afternoon: the same in-game day throughout
        view = begin_turn(state, f"Chat number {turn}.", 0)
        beats += len(_compete_lines(view))
    assert 1 <= beats <= 2, f"{beats} compete beats in one day for two rivals (one each at most)"


def test_a_new_day_lets_the_rival_try_again():
    model = _model({"makoto": "kitchen", "minori": "kitchen"})
    _set(model, "minori", "player", 50)
    _set(model, "makoto", "minori", 48)
    state = _terrace_state(model)
    assert _compete_lines(begin_turn(state, "Morning.", 0))
    assert not _compete_lines(begin_turn(state, "Still the same day.", 0))
    model.world.minute += 24 * 60
    state.minute = model.world.minute
    assert _compete_lines(begin_turn(state, "The next morning.", model.world.minute - 5))


# ---------------------------------------------------------------- P-08 slice 3: first moves wait for acquaintance
def _strangers(state, model):
    for cid in model.characters:
        model.first_met_day.pop(cid, None)
        model.turns_together[cid] = 0


def test_a_stranger_has_no_crush_on_the_player_so_a_day_zero_move_never_comes():
    model = _model({"minori": "kitchen", "makoto": "kitchen"})
    _set(model, "minori", "player", 80)
    state = _terrace_state(model)
    _strangers(state, model)
    view = begin_turn(state, "Hello.", 0)
    assert not model.stances.has("minori", "crush", "player")
    assert not any(i.kind == "pursue" and i.target == "player" for i in model.agendas.get("minori", []))
    assert not any("drawn to" in line for line in view.must_address)
    for cid in model.characters:                  # ten turns together later they are past strangers
        model.turns_together[cid] = 12
    begin_turn(state, "Hello again.", 0)
    assert model.stances.has("minori", "crush", "player")


def test_a_story_with_no_acquaintance_levels_does_not_gate_a_crush():
    model = _model({"minori": "kitchen"})
    _set(model, "minori", "player", 80)
    cfg = copy.deepcopy(TERRACE)
    cfg.pop("acquaintance", None)
    state = _terrace_state(model)
    state.story_cfg = cfg
    _strangers(state, model)
    begin_turn(state, "Hello.", 0)
    assert model.stances.has("minori", "crush", "player")


def test_one_unsolicited_move_per_person_per_day_covers_every_kind_of_beat():
    model = _model({"minori": "kitchen"})
    _set(model, "minori", "player", 80)
    state = _terrace_state(model)
    first = begin_turn(state, "Morning.", 0)
    second = begin_turn(state, "Still morning.", 0)
    assert model.initiative_last_day.get("beat:minori") == 0, "the first turn spent her move for the day"
    assert not any("as if offhand" in l or "interest" in l for l in second.must_address)


# ---------------------------------------------------------------- stances reach the prompt through the person's card
def _card(view, name):
    return next(card for card in view.cards if card.startswith(name))


def test_a_present_persons_card_carries_their_own_stances_toward_people_in_the_room():
    model = _model({"makoto": "kitchen", "uchi": "kitchen", "minori": "kitchen"})
    _set(model, "makoto", "minori", 48)
    _set(model, "uchi", "minori", 47)
    state = _terrace_state(model)
    view = begin_turn(state, "Hello.", 0)
    card = _card(view, "Makoto")
    assert "attitudes (show, never state)" in card and "quietly drawn to Minori" in card
    assert "rival for Minori" in card and "Uchi" in card


def test_a_romantic_stance_toward_the_player_stays_off_the_card():
    model = _model({"minori": "kitchen", "makoto": "kitchen"})
    _set(model, "minori", "player", 80)
    _set(model, "makoto", "minori", 48)
    state = _terrace_state(model)
    view = begin_turn(state, "Hello.", 0)
    assert model.stances.has("minori", "crush", "player")
    assert "drawn to Paul" not in _card(view, "Minori") and "attitudes" not in _card(view, "Minori")


def test_a_hidden_standing_of_someone_else_never_reaches_a_card():
    model = _model({"makoto": "kitchen", "minori": "kitchen"})
    _set(model, "minori", "makoto", 60)            # Minori's own feeling; Makoto has none of his own
    state = _terrace_state(model)
    view = begin_turn(state, "Hello.", 0)
    assert "attitudes" not in _card(view, "Makoto")

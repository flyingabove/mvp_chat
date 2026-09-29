"""BL-39 phase D: one event, a different human reaction from each perceiver."""
from types import SimpleNamespace

import pytest

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.rules.personality import Personality, Temperament, personalities, personality_for
from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.appraisal import appraise_behaviors
from backend.app.engine.world_model.turn import begin_turn, record_behaviors

from tests.backend.app.engine.world_model.helpers import make_model

CFG = {"social_tracks": {
    "tracks": [{"id": "romance", "daily_gain_cap": 50, "repeat_decay": 0.5,
                "tiers": [{"id": "strangers", "floor": 0, "ceiling": 25},
                          {"id": "interested", "floor": 25, "ceiling": 60}]}],
    "appraisal": {"track": "romance", "gain_scale": 3, "witness_scale": 0.5, "feeling_scale": 0.02,
                  "romantic_tags": ["flirtatious"], "jealousy_tier": "interested", "eligible": "opposite_gender"},
}}
GENDERS = {"player": "M", "ann": "F", "cat": "F", "ben": "M"}


def Tag(frm, to, tag):
    return SimpleNamespace(from_id=frm, to_id=to, tag=tag)


def _run(model, behaviors, people=None, turn="1", graph=None, genders=GENDERS):
    rules = social_rules(CFG)
    people = people or {"ann": Personality(tastes={"flirtatious": 1.0}),
                        "cat": Personality(Temperament(jealousy=0.9), {"flirtatious": -1.0}),
                        "ben": Personality(tastes={"flirtatious": 2.0})}
    return appraise_behaviors(model, rules, people, behaviors, set(model.present_with_player()), graph,
                              turn_key=turn, genders=genders)


def _value(model, owner, target="player"):
    standing = model.standing.get(owner, target, "romance")
    return standing.value if standing else 0.0


def test_one_flirt_produces_different_reactions_from_target_rival_and_same_gender_witness():
    model = make_model({"ann": "kitchen", "cat": "kitchen", "ben": "kitchen"})
    _run(model, [Tag("player", "ann", "flirtatious")])
    assert _value(model, "ann") == 3.0, "the target likes it: taste 1 x scale 3"
    assert _value(model, "cat") == 0.0, "cat dislikes flirting but a loss from zero stays zero"
    assert model.standing.get("ben", "player", "romance") is None, "same gender: romance track does not apply"


def test_a_partner_who_watches_a_flirt_elsewhere_gets_jealous():
    model = make_model({"ann": "kitchen", "cat": "kitchen"})
    graph = CharacterGraph.from_dict({"edges": [{"from_id": "cat", "to_id": "player", "state": {"trust": 0.5}}]})
    rules = social_rules(CFG)
    model.standing.bind(rules.tracks)
    from backend.app.engine.world_model.standing import Standing
    model.standing.standings[("cat", "player", "romance")] = Standing(value=40.0)
    _run(model, [Tag("player", "ann", "flirtatious")], graph=graph)
    assert _value(model, "cat") == pytest.approx(40 - 3 * 0.9)
    edge = graph.get_edge("cat", "player").state
    assert edge.jealousy == pytest.approx(0.09) and edge.trust == pytest.approx(0.5 - 0.045)


def test_a_rude_act_hurts_more_for_an_unforgiving_target():
    def after_rudeness(forgiveness):
        model = make_model({"ann": "kitchen"})
        people = {"ann": Personality(Temperament(forgiveness=forgiveness), {"rude": -1.0, "warm": 5 / 3})}
        _run(model, [Tag("player", "ann", "warm")], people)
        _run(model, [Tag("player", "ann", "rude")], people, turn="2")
        return _value(model, "ann")
    assert after_rudeness(0.0) == pytest.approx(5 - 3 * 1.5)
    assert after_rudeness(1.0) == pytest.approx(5 - 3 * 0.5)


def test_absent_people_do_not_react_and_nobody_judges_their_own_act():
    model = make_model({"ann": "kitchen", "cat": "garden"})
    _run(model, [Tag("player", "ann", "flirtatious"), Tag("ann", "player", "flirtatious")])
    assert model.standing.get("cat", "player", "romance") is None
    assert model.standing.get("ann", "ann", "romance") is None
    assert _value(model, "ann") == 3.0


def test_npc_to_npc_acts_build_npc_tracks():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    _run(model, [Tag("ben", "ann", "flirtatious")])
    assert _value(model, "ann", "ben") == 3.0


def test_no_behavior_tags_means_no_change_and_replays_are_idempotent():
    model = make_model({"ann": "kitchen"})
    graph = CharacterGraph.from_dict({"edges": [{"from_id": "ann", "to_id": "player", "state": {}}]})
    assert _run(model, [], graph=graph) == []
    _run(model, [Tag("player", "ann", "flirtatious")], graph=graph)
    _run(model, [Tag("player", "ann", "flirtatious")], graph=graph)
    assert _value(model, "ann") == 3.0
    assert graph.get_edge("ann", "player").state.affection == pytest.approx(0.02), "feelings apply once"
    assert len(model.appraised_events) == 1


def test_unknown_people_and_blank_tags_are_ignored():
    model = make_model({"ann": "kitchen"})
    assert _run(model, [Tag("stranger", "ann", "warm"), Tag("player", "ann", ""), Tag("ann", "ann", "warm")]) == []


def test_renaming_ids_does_not_change_the_mechanics():
    def run(a, b):
        model = make_model({a: "kitchen", b: "kitchen"})
        people = {a: Personality(tastes={"warm": 1.0}), b: Personality(tastes={"warm": 0.5})}
        _run(model, [Tag("player", a, "warm")], people, genders={"player": "M", a: "F", b: "F"})
        return _value(model, a), _value(model, b)
    assert run("ann", "cat") == run("zoe", "yui")


def test_record_behaviors_is_inert_for_stories_without_tracks():
    model = make_model({"ann": "kitchen"})
    state = SimpleNamespace(world_model=model, story_cfg={"world_model": {"enabled": True}}, characters={},
                            character_graph=None, gender="M")
    assert record_behaviors(state, [Tag("player", "ann", "warm")]) == []


def test_private_talk_is_recorded_only_one_on_one():
    model = make_model({"ann": "kitchen", "ben": "living_room"})
    state = SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul",
                            story_cfg={"world_model": {"enabled": True}}, characters=model.characters,
                            cast_lifecycle=None, character_graph=None)
    begin_turn(state, "Can we talk?", 0)
    assert [e.participants for e in model.world.events if e.kind == "private_talk"] == [("player", "ann")]
    model.world.move("ben", "kitchen")
    begin_turn(state, "Hi Ben.", 0)
    assert len([e for e in model.world.events if e.kind == "private_talk"]) == 1


def test_personalities_layer_character_over_story_defaults_and_validate():
    cfg = {"behavior_tag_vocabulary": ["warm", "rude"],
           "default_personality": {"temperament": {"jealousy": 0.2}, "tastes": {"warm": 1.0, "rude": -1.0}},
           "characters": [{"key": "ann"}, {"key": "ben", "personality": {"tastes": {"warm": 2.0}}}],
           "personalities": {"ann": {"temperament": {"pride": 0.9}}}}
    people = personalities(cfg)
    assert people["ann"].temperament.jealousy == 0.2 and people["ann"].temperament.pride == 0.9
    assert people["ben"].taste("warm") == 2.0 and people["ben"].taste("rude") == -1.0
    for bad in ({"personality": {"tastes": {"sneaky": 1.0}}}, {"personality": {"tastes": {"warm": 9}}},
                {"personality": {"temperament": {"pride": 1.5}}}, {"personality": {"temperament": {"mood": 0.1}}}):
        with pytest.raises(ValueError):
            personality_for(cfg, {"key": "x", **bad})
    with pytest.raises(ValueError):
        personalities({**cfg, "personalities": {"nobody": {}}})


def test_terrace_content_is_complete_and_valid():
    cfg = build_story_registry()["six_strangers"]["raw"]
    people = personalities(cfg)
    assert len(people) == 17 and set(cfg["personalities"]) == set(people)
    rules = social_rules(cfg)
    assert rules.appraisal.track == "romance" and rules.appraisal.eligible == "opposite_gender"
    assert [t.id for t in rules.tracks["romance"].tiers] == ["strangers", "friends", "interested", "dating", "committed"]
    assert rules.requirements_for("minori", "romance") == (), "no invented dealbreakers"
    assert len({tuple(sorted(p.tastes.items())) for p in people.values()}) > 10, "characters are distinct"


def test_the_mystery_uses_neutral_defaults_and_no_tracks():
    cfg = build_story_registry()["iu_murder_mystery"]["raw"]
    assert social_rules(cfg) is None
    assert all(p == Personality() for p in personalities(cfg).values())

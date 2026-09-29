"""BL-39 phase E: self-claims, per-listener belief, disputes, tells and disclosure."""
from collections import Counter
from types import SimpleNamespace

import pytest

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.extractors.turn_extractor import SelfClaimUpdate, TurnExtractor
from backend.app.engine.rules.conditions import Viewpoint, parse
from backend.app.engine.rules.personality import personalities
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.deception import DeceptionProfile, audible, choose_cue, show_probability
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.persona import PersonaBook, SelfClaim
from backend.app.engine.world_model.turn import begin_turn, record_claims

from tests.backend.app.engine.world_model.helpers import make_model

CFG = {"world_model": {"enabled": True}, "player_fact_keys": ["height", "smokes"],
       "personalities": {"ann": {"temperament": {"skepticism": 1.0}}},
       "characters": [{"key": "ann"}, {"key": "ben"}, {"key": "cat"}]}


def _state(model, graph=None, cfg=CFG, tells=None):
    profiles = {cid: SimpleNamespace(name=cid.title(), tells=(tells or {}).get(cid, [])) for cid in model.characters}
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters=profiles, cast_lifecycle=None, character_graph=graph, gender="M")


def _claim(key, value, correction=False):
    return SelfClaimUpdate(key, value, correction)


def test_only_present_people_hear_a_claim_and_believe_it():
    model = make_model({"ann": "kitchen", "cat": "garden"})
    record_claims(_state(model), [_claim("height", "180cm")], message="I'm 180cm tall.")
    assert model.persona.belief("ann", "player", "height").value == "180cm"
    assert model.persona.belief("cat", "player", "height").status == "unknown"
    assert model.persona.first("player", "height").audience == ("ann",)
    assert any(m.kind == "claim" for m in model.memories.of("ann"))


def test_an_explicit_correction_updates_belief_without_a_dispute():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_claims(state, [_claim("height", "180cm")], message="I'm 180cm.")
    model.turn += 1
    disputes = record_claims(state, [_claim("height", "175cm", correction=True)], message="Actually I'm 175cm.")
    assert disputes == []
    belief = model.persona.belief("ann", "player", "height")
    assert (belief.status, belief.value, belief.corrected) == ("accepted", "175cm", True)
    assert model.persona.first("player", "height").value == "180cm", "first claim stays as history"


def test_conflicting_claims_dispute_the_belief_and_raise_suspicion_by_skepticism():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    graph = CharacterGraph.from_dict({"edges": [{"from_id": "ann", "to_id": "player", "state": {}},
                                                {"from_id": "ben", "to_id": "player", "state": {}}]})
    state = _state(model, graph)
    record_claims(state, [_claim("smokes", "no")], message="No, I don't smoke.")
    model.turn += 1
    disputes = record_claims(state, [_claim("smokes", "yes")], message="Yes, I smoke sometimes.")
    assert sorted(disputes) == [("ann", "smokes"), ("ben", "smokes")]
    assert model.persona.belief("ann", "player", "smokes").status == "disputed"
    assert graph.get_edge("ann", "player").state.suspicion == pytest.approx(0.1)
    assert graph.get_edge("ben", "player").state.suspicion == pytest.approx(0.05)
    assert len([e for e in model.world.events if e.kind == "claim_dispute"]) == 2
    assert not any("lie" in e.truth for e in model.world.events), "a dispute is not declared a lie"


def test_claims_must_be_grounded_keyed_and_are_recorded_once():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_claims(state, [_claim("height", "190cm"), _claim("salary", "a lot")], message="I'm 180cm.")
    assert model.persona.claims == []
    record_claims(state, [_claim("height", "180cm")], message="I'm 180cm.")
    record_claims(state, [_claim("height", "180cm")], message="I'm 180cm.")
    assert len(model.persona.claims) == 1


def test_yes_no_facts_are_grounded_by_the_facts_own_word():
    """Live play: "I don't smoke" -> smokes=no was dropped because "no" is not in the message."""
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_claims(state, [_claim("smokes", "no")], message="Hi, I'm Paul and I don't smoke.")
    model.turn += 1
    record_claims(state, [_claim("smokes", "yes")], message="Honestly I smoke a pack a day.")
    assert [c.value for c in model.persona.claims] == ["no", "yes"]
    model.turn += 1
    record_claims(state, [_claim("smokes", "yes")], message="I love hiking.")
    assert len(model.persona.claims) == 2, "a fact never mentioned is not grounded"


def test_believed_attribute_reads_the_holders_belief_never_the_truth():
    model = make_model({"ann": "kitchen", "cat": "garden"})
    record_claims(_state(model), [_claim("height", "185")], message="I'm 185.")
    tall = parse({"kind": "believed_attribute", "key": "height", "op": ">=", "value": 180})
    assert tall.evaluate(Viewpoint(model=model, holder="ann", subject="player")) is True
    assert tall.evaluate(Viewpoint(model=model, holder="cat", subject="player")) is None
    assert tall.evaluate(Viewpoint(model=model, holder=None, subject="player")) is None
    listed = parse({"kind": "believed_attribute", "key": "height", "op": "in", "value": ["185", "190"]})
    assert listed.evaluate(Viewpoint(model=model, holder="ann", subject="player")) is True
    with pytest.raises(ValueError):
        parse({"kind": "believed_attribute", "key": "height", "op": "in", "value": 185})


def test_persona_round_trips_with_the_world_model():
    model = make_model({"ann": "kitchen"})
    record_claims(_state(model), [_claim("height", "180cm")], message="I'm 180cm.")
    assert WorldModel.from_dict(model.to_dict()).persona.to_dict() == model.persona.to_dict()


def test_skill_and_pressure_change_how_often_a_tell_shows():
    cues = ["voice tremor on logistics questions"]
    def rate(skill, message, questioned=True):
        profile = DeceptionProfile(skill=skill, composure=skill)
        shown = Counter(choose_cue(profile, cues, message, questioned, f"seed{i}") is not None for i in range(400))
        return shown[True] / 400
    pressed, calm = "Walk me through the logistics that night.", "Nice weather."
    assert rate(0.1, pressed) > rate(0.9, pressed) > 0, "skilled liars show less, but not never"
    assert rate(0.1, pressed) > rate(0.1, calm, questioned=False), "pressure exposes"
    assert show_probability(DeceptionProfile(1.0, 1.0), 0.1) == 0.0


def test_tells_are_seeded_and_voice_only_calls_hide_visual_cues():
    cues = ["unblinking when confronted with timelines", "redirects to 'mental health' narratives"]
    profile = DeceptionProfile(0.0, 0.0)
    first = choose_cue(profile, cues, "Check the timelines.", True, "s1")
    assert first == choose_cue(profile, cues, "Check the timelines.", True, "s1")
    assert audible(cues[1]) and not audible(cues[0])
    for i in range(50):
        assert choose_cue(profile, cues, "Check the timelines.", True, f"s{i}", voice_only=True) in (None, cues[1])


def test_a_pressed_suspect_shows_a_tell_as_behavior_not_a_verdict():
    model = make_model({"ann": "kitchen"})
    cfg = {**CFG, "personalities": {"ann": {"deception": {"skill": 0.0, "composure": 0.0}}}}
    state = _state(model, cfg=cfg, tells={"ann": ["nervous about CCTV near side entrance"]})
    shown = []
    for turn in range(20):
        begin_turn(state, "Ann, were you near the CCTV at the side entrance?", 0)
        shown += [line for line in model.view.must_address if "small tell" in line]
    assert shown and all("proves nothing" in line and "lying" not in line for line in shown)


def test_requirement_tells_reach_the_scene_only_when_disclosure_allows():
    tracks = {"tracks": [{"id": "romance", "tiers": [{"id": "s", "floor": 0, "ceiling": 50}]}],
              "requirements": {"ann": [
                  {"id": "tall", "track": "romance", "tier": "s", "disclosure": "hint",
                   "tell": "cools noticeably when height comes up",
                   "condition": {"kind": "believed_attribute", "key": "height", "op": ">=", "value": 180}},
                  {"id": "secret", "track": "romance", "tier": "s", "disclosure": "hidden", "tell": "HIDDEN",
                   "condition": {"kind": "believed_attribute", "key": "height", "op": ">=", "value": 180}}]}}
    model = make_model({"ann": "kitchen"})
    state = _state(model, cfg={**CFG, "social_tracks": tracks})
    begin_turn(state, "Hi.", 0)
    assert not any("cools" in line for line in model.view.must_address), "unknown belief: no hint"
    record_claims(state, [_claim("height", "170")], message="I'm 170.")
    begin_turn(state, "So anyway.", 0)
    assert any("cools noticeably when height comes up. Do not state the reason." in l
               for l in model.view.must_address)
    assert not any("HIDDEN" in line for line in model.view.must_address)


def test_extractor_parses_self_claims_and_lists_fact_keys():
    parsed = TurnExtractor._parse_dict({"self_claims": [{"key": "Height", "value": " 180 cm ", "correction": 1},
                                                        {"key": "", "value": "x"}]}, set(), set())
    assert parsed.self_claims == [SelfClaimUpdate("height", "180 cm", True)]


def test_content_declares_fact_keys_and_suspect_deception():
    terrace = build_story_registry()["six_strangers"]["raw"]
    assert "height" in terrace["player_fact_keys"]
    iu = build_story_registry()["iu_murder_mystery"]["raw"]
    people = personalities(iu)
    assert people["han_jae_seo"].deception.skill > people["yoo_min_ho"].deception.skill

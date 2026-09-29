"""BL-39 phase J: seeded month-long Terrace campaigns through the real turn pipeline.

No model calls: extraction is scripted and the storyteller is faked, so these
prove the rules (earned win, director cut, solo exit on both player-gender
paths), not prose quality.
"""
import types

import pytest
from fastapi.testclient import TestClient

from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate, SocialActUpdate, TurnExtraction


@pytest.fixture()
def campaign(monkeypatch, tmp_path):
    from backend.app.api import prompt_engine as pe
    from backend.app.db import database, repos

    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "storieschat.db")
    monkeypatch.setattr(repos, "DATA_DIR", tmp_path)
    database.init_db()
    monkeypatch.setattr(pe, "retrieve_knowledge", lambda *a, **k: ([], {}), raising=False)

    class Resp:
        status_code, text = 200, "ok"

        def json(self):
            return {"choices": [{"message": {"content": "*ok*\n\n**\"hi\"**\n[[STATE]]{\"emotion\":\"calm\",\"rel_delta\":0}[[/STATE]]"}}],
                    "usage": {"total_tokens": 1}}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, *a, **k):
            return Resp()

    monkeypatch.setattr(pe.httpx, "AsyncClient", Client)

    async def noop(*a, **k):
        return []

    monkeypatch.setattr(pe, "extract_facts_from_message", noop, raising=False)
    script = []

    async def extract(*a, **k):
        return script.pop(0) if script else TurnExtraction()

    monkeypatch.setattr(pe._TURN_EXTRACTOR, "extract", extract)
    from backend.app import main
    return types.SimpleNamespace(pe=pe, client=TestClient(main.app), script=script)


def _new_game(c, sid, gender):
    r = c.client.post("/api/chat", json={"session_id": sid, "message": f"__cmd_newgame__:six_strangers|{gender}|Sam"})
    assert r.status_code == 200
    return c.pe.SESSIONS[sid]["state"]


def _say(c, sid, message="Hi."):
    return c.client.post("/api/chat", json={"session_id": sid, "message": message}).json()


def test_a_passive_player_is_eventually_cut_by_the_director(campaign):
    state = _new_game(campaign, "passive", "M")
    ending = None
    for _ in range(120):   # casts are random; the cut should come within a few in-game months
        body = _say(campaign, "passive", "__cmd_skip__:DAY")
        ending = body.get("ending") or ending
        if ending:
            break
    model = campaign.pe.SESSIONS["passive"]["state"].world_model
    assert model.counters.get("couples_left", 0) >= 3, f"NPC couples never left: {model.npc_couples}"
    assert ending and ending["id"] == "cut_by_director" and ending["kind"] == "loss"


@pytest.mark.parametrize("gender", ["M", "F"])
def test_a_strategic_player_can_earn_the_win_on_both_gender_paths(campaign, gender):
    sid = f"strategic_{gender}"
    state = _new_game(campaign, sid, gender)
    genders = {c["key"]: c["gender"] for c in state.story_cfg["characters"]}
    target = next(c for c in state.cast_lifecycle.active_ids() if genders.get(c) not in ("", gender))
    ending, confessed = None, False
    for day in range(40):
        live = campaign.pe.SESSIONS[sid]["state"]
        model = live.world_model
        place = model.world.place_of(target)
        if place and live.location_id != place:
            live.location_id = place                   # the player seeks the target out
        standing = model.standing.get(target, "player", "romance")
        value = standing.value if standing else 0
        act = None
        if not confessed and model.standing.tier_reached(target, "player", "romance", "interested"):
            act = SocialActUpdate("confess", target)
        elif confessed and value >= 70:
            act = SocialActUpdate("ask_leave_together", target)
        campaign.script.append(TurnExtraction(
            behavior_tags=[BehaviorTagUpdate("player", target, "supportive_of_goals"),
                           BehaviorTagUpdate("player", target, "attentive")],
            social_act=act))
        body = _say(campaign, sid, f"I'm here for you, {target}.")
        confessed = confessed or model.romance_relationship_partner == target
        ending = body.get("ending")
        if ending:
            break
        campaign.script.append(TurnExtraction())
        _say(campaign, sid, "__cmd_skip__:DAY")
    assert ending and ending["id"] == "left_together", \
        f"no win in 40 days (confessed={confessed}, standing={campaign.pe.SESSIONS[sid]['state'].world_model.standing.get(target, 'player', 'romance')})"


def test_leaving_alone_is_available_on_day_one(campaign):
    _new_game(campaign, "solo", "F")
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("leave_alone")))
    body = _say(campaign, "solo", "I'm leaving the house alone.")
    assert body["ending"]["id"] == "left_alone"
    assert any(s.get("speaker_name") == "Yukiko Ehara" for s in body["segments"]), "the panel closes the run"

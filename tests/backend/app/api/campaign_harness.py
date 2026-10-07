"""The seeded Terrace campaign rig (no model calls: scripted extraction, faked storyteller), shared by the campaign tests
and `scripts/sweep_terrace_difficulty.py`."""
import random
import types

from fastapi.testclient import TestClient

from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate, SocialActUpdate, TurnExtraction


def make_campaign(monkeypatch, tmp_path, seed=0):
    from backend.app.api import prompt_engine as pe
    from backend.app.db import database, repos
    from backend.app.engine import cast_lifecycle

    # The opening roster is drawn with secrets.SystemRandom, so an unseeded campaign
    # was a different house every run and the passive-cut test failed ~1 in 3 on the
    # Railway build (2026-09-29). Seed 0 is one of the slowest houses measured.
    monkeypatch.setattr(cast_lifecycle.secrets, "SystemRandom", lambda: random.Random(seed))

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


def new_game(c, sid, gender, rival_aim=None):
    """Start a Terrace game; `rival_aim` (0-1) re-tunes how hard each rival starts out chasing someone (a sweep knob)."""
    r = c.client.post("/api/chat", json={"session_id": sid, "message": f"__cmd_newgame__:six_strangers|{gender}|Sam"})
    assert r.status_code == 200
    state = c.pe.SESSIONS[sid]["state"]
    if rival_aim is not None:
        state.story_cfg["social_tracks"]["couples"]["rival_aim"] = rival_aim
        state.world_model.agendas.clear()                  # the next turn seeds every rival's aim at the new strength
    return state


def say(c, sid, message="Hi."):
    return c.client.post("/api/chat", json={"session_id": sid, "message": message}).json()


def run_passive(c, sid, gender="M", cap=180, rival_aim=None):
    """A player who only skips days. Returns {"ending", "day", "couples_left"}."""
    new_game(c, sid, gender, rival_aim)
    ending, day = None, 0
    for day in range(1, cap + 1):
        ending = say(c, sid, "__cmd_skip__:DAY").get("ending") or ending
        if ending:
            break
    model = c.pe.SESSIONS[sid]["state"].world_model
    return {"ending": ending, "day": day, "couples_left": model.counters.get("couples_left", 0), "npc_couples": model.npc_couples}


def run_strategic(c, sid, gender, days=40, rival_aim=None):
    """A player who seeks one eligible resident out, earns their standing, confesses and asks them to leave together.
    Returns {"ending", "day", "confessed", "target", "standing", "target_coupled"}."""
    state = new_game(c, sid, gender, rival_aim)
    genders = {ch["key"]: ch["gender"] for ch in state.story_cfg["characters"]}
    target = next(ch for ch in state.cast_lifecycle.active_ids() if genders.get(ch) not in ("", gender))
    ending, confessed, day = None, False, 0
    for day in range(1, days + 1):
        live = c.pe.SESSIONS[sid]["state"]
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
        c.script.append(TurnExtraction(
            behavior_tags=[BehaviorTagUpdate("player", target, "supportive_of_goals"),
                           BehaviorTagUpdate("player", target, "attentive")],
            social_act=act))
        body = say(c, sid, f"I'm here for you, {target}.")
        confessed = confessed or model.romance_relationship_partner == target
        if body.get("pending_choice"):
            # BL-46: her yes opens a choice card; the win plays when the player confirms leaving.
            assert body["pending_choice"]["id"] == "leave_together" and "ending" not in body
            body = say(c, sid, "__choice__:leave_together:leave_now")
        ending = body.get("ending")
        if ending:
            break
        c.script.append(TurnExtraction())
        say(c, sid, "__cmd_skip__:DAY")
    model = c.pe.SESSIONS[sid]["state"].world_model
    standing = model.standing.get(target, "player", "romance")
    return {"ending": ending, "day": day, "confessed": confessed, "target": target, "standing": standing,
            "target_coupled": any(target in key.split("|") for key in model.npc_couples)}

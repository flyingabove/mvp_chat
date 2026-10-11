"""P-03: a golden record of what today's seeded Terrace NPCs decide, day by day (the refactor safety net).

Stances (P-08) and scenes (P-11) replace several hand-coded decision paths. This test replays seeded campaigns through
the real turn pipeline with no model calls and compares, per story day, each character's intentions, the beat offered,
invitations, off-screen outcomes, fallout, couples and the director clock with the committed record in
`golden/terrace_decisions.json`.

A deliberate behaviour change must regenerate the record IN THE SAME COMMIT, with the reason in the commit message:
    UPDATE_DECISION_GOLDEN=1 python -m pytest tests/backend/app/engine/world_model/test_decision_golden.py
"""
import difflib
import json
import os
import random
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.engine.extractors.turn_extractor import SocialActUpdate, TurnExtraction

GOLDEN = Path(__file__).parent / "golden" / "terrace_decisions.json"
SEEDS = range(12)
GENDERS = ("M", "F")
DAYS = 6                          # every seeded house, both genders: enough for beats, fallout and off-screen life
LONG_RUNS = {(11, "F"): 30}       # the one house that forms an NPC couple (day 12): follow it to departure


class _Recorder:
    """Wraps the real decision functions; each call is recorded, then delegated unchanged."""

    def __init__(self):
        self.events: list = []

    def wrap(self, monkeypatch, owner, name, summarize):
        real = getattr(owner, name)

        def wrapper(*args, **kwargs):
            result = real(*args, **kwargs)
            summarize(self.events, args, result)
            return result

        monkeypatch.setattr(owner, name, wrapper)

    def drain(self) -> list:
        events, self.events = self.events, []
        return events


def _intentions(model, day):
    out = {}
    for cid in sorted(model.agendas):
        live = sorted((i.kind, i.target, round(i.priority, 3)) for i in model.agendas[cid] if i.expires_day >= day)
        if live:
            out[cid] = [list(row) for row in live]
    return out


def _standings(model):
    """Every non-zero standing, rounded: what fallout, off-screen life and the player's acts did to each pair."""
    rows = {f"{owner}>{target}:{track}": round(standing.value, 2)
            for (owner, target, track), standing in sorted(model.standing.standings.items()) if round(standing.value, 2)}
    return rows


def _agreements(model):
    book = model.agreements.to_dict()
    items = book.get("agreements", book) if isinstance(book, dict) else book
    rows = items.values() if isinstance(items, dict) else items
    return sorted((str(a.get("proposer")), str(a.get("counterpart")), str(a.get("activity")), str(a.get("status")))
                  for a in rows if isinstance(a, dict))


def _day_record(model, active, events):
    day = model.world.day_index(model.world.minute)
    return {
        "day": day,
        "intentions": _intentions(model, day),
        "events": events,
        "standings": _standings(model),
        "agreements": [list(row) for row in _agreements(model)],
        "couples": sorted(model.npc_couples.items()),
        "departed": sorted(model.departed_couples),
        "director_clock": dict(sorted(model.counters.items())),
        "cast": sorted(active),
    }


@pytest.fixture()
def world(monkeypatch, tmp_path):
    from backend.app.api import prompt_engine as pe
    from backend.app.db import database, repos
    from backend.app.engine import cast_lifecycle
    from backend.app.engine.world_model import act_fallout, turn

    seed = {"value": 0}
    monkeypatch.setattr(cast_lifecycle.secrets, "SystemRandom", lambda: random.Random(seed["value"]))
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
    script: list = []

    async def extract(*a, **k):
        return script.pop(0) if script else TurnExtraction()

    monkeypatch.setattr(pe._TURN_EXTRACTOR, "extract", extract)

    recorder = _Recorder()
    recorder.wrap(monkeypatch, turn, "resolve_offscreen", lambda ev, args, outcomes: ev.extend(
        ["offscreen", o.kind, sorted((o.encounter.a, o.encounter.b)), o.encounter.place] for o in outcomes))
    recorder.wrap(monkeypatch, turn, "next_beat", lambda ev, args, beat: ev.append(
        ["beat", beat[0], beat[1].kind, beat[1].target]) if beat else None)
    recorder.wrap(monkeypatch, turn, "queue_contacts", lambda ev, args, queued: ev.extend(
        ["invitation", str(getattr(c, "sender", "")), str(getattr(c, "intent", ""))] for c in queued))
    real_fallout = act_fallout.apply_fallout

    def fallout(state, track, kind, target, answer, witnesses, cause_event_id):
        """Record the call AND what it proposed (the standing loss can be clamped to nothing, so values alone hide it)."""
        book = state.world_model.standing
        before = book.sequence
        real_fallout(state, track, kind, target, answer, witnesses, cause_event_id)
        effects = [[e.owner, e.target, e.tag, round(e.proposed, 3), round(e.applied, 3)]
                   for e in book.journal if e.sequence > before]
        recorder.events.append(["fallout", track, kind, target, answer, sorted(witnesses), effects])

    monkeypatch.setattr(act_fallout, "apply_fallout", fallout)
    # The intentions fallout adds (a rival who sees an opening) are in the daily intentions record.

    from backend.app import main
    return types.SimpleNamespace(pe=pe, client=TestClient(main.app), script=script, seed=seed, recorder=recorder)


def _say(w, sid, message):
    r = w.client.post("/api/chat", json={"session_id": sid, "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def _campaign(w, seed, gender, days_to_run):
    """A passive player (skips whole days); one scripted public confession on day 3 gives fallout a chance to run."""
    w.seed["value"] = seed
    sid = f"golden_{seed}_{gender}"
    _say(w, sid, f"__cmd_newgame__:six_strangers|{gender}|Sam")
    days, w.recorder.events = [], []
    for step in range(days_to_run):
        state = w.pe.SESSIONS[sid]["state"]
        if step == 3:
            _scripted_confession(w, sid, state, gender)
        body = _say(w, sid, "__cmd_skip__:DAY")
        state = w.pe.SESSIONS[sid]["state"]
        days.append(_day_record(state.world_model, state.cast_lifecycle.active_ids(), w.recorder.drain()))
        if body.get("ending"):
            days[-1]["ending"] = body["ending"]["id"]
            break
    return days


def _scripted_confession(w, sid, state, gender):
    model = state.world_model
    genders = {c["key"]: c["gender"] for c in state.story_cfg["characters"]}
    target = next((c for c in sorted(state.cast_lifecycle.active_ids()) if genders.get(c) not in ("", gender)), None)
    place = model.world.place_of(target) if target else None
    if place:
        state.location_id = place
        w.script.append(TurnExtraction(social_act=SocialActUpdate("confess", target)))
        _say(w, sid, f"{target}, I have to tell you something.")
        w.recorder.events.append(["scripted", "confess", target])


def _record(w):
    return {f"seed{seed}_{gender}": _campaign(w, seed, gender, LONG_RUNS.get((seed, gender), DAYS))
            for seed in SEEDS for gender in GENDERS}


def _dump(data) -> str:
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def test_seeded_terrace_decisions_match_the_golden_record(world):
    actual = _dump(_record(world))
    if os.environ.get("UPDATE_DECISION_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(actual, encoding="utf-8", newline="\n")
    expected = GOLDEN.read_text(encoding="utf-8") if GOLDEN.exists() else ""
    if actual != expected:
        diff = list(difflib.unified_diff(expected.splitlines(), actual.splitlines(), "golden", "now", n=2, lineterm=""))
        shown = "\n".join(diff[:60]) + (f"\n... {len(diff) - 60} more diff lines" if len(diff) > 60 else "")
        pytest.fail(
            "Seeded Terrace NPC decisions changed (P-03 golden record).\n"
            "If this change is deliberate, regenerate the record IN THE SAME COMMIT and put the reason in the message:\n"
            "    UPDATE_DECISION_GOLDEN=1 python -m pytest tests/backend/app/engine/world_model/test_decision_golden.py\n"
            "If it is not deliberate, a refactor changed behaviour: find out why.\n\n" + shown)

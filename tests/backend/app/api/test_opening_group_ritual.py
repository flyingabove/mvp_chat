"""BL-78: the show's "what's your type?" round reaches the storyteller exactly once, after the last arrival.

Runs the real Terrace opening through /api/chat with scripted model calls. The brief is built from each resident's own
authored tastes and must not repeat on later turns, nor replay into a restored mid-game save.
"""
from tests.backend.app.api.test_terrace_campaigns import _new_game, _say, campaign  # noqa: F401  (scripted fixture)

MARK = "Group moment, once"


def _capture(campaign, monkeypatch):
    sent = []
    base = campaign.pe.httpx.AsyncClient

    class Recording(base):
        async def post(self, *args, **kwargs):
            sent.append(kwargs.get("json"))
            return await super().post(*args, **kwargs)

    monkeypatch.setattr(campaign.pe.httpx, "AsyncClient", Recording)
    return sent


def _briefed_turns(campaign, sid, turns):
    seen = []
    for _ in range(turns):
        _say(campaign, sid, "Hello, nice to meet everyone.")
        state = campaign.pe.SESSIONS[sid]["state"]
        seen.append(bool(state.opening_ritual_brief))
    return seen


def test_the_type_round_is_briefed_once_after_everyone_has_arrived(campaign, monkeypatch):
    sent = _capture(campaign, monkeypatch)
    state = _new_game(campaign, "ritual", "M")
    assert state.opening_ritual_done is False
    seen = _briefed_turns(campaign, "ritual", 16)
    assert seen.count(True) == 1, f"exactly one briefed turn, got {seen}"
    state = campaign.pe.SESSIONS["ritual"]["state"]
    assert state.opening_ritual_done is True
    assert set(state.opening_arrival_minutes) <= set(state.opening_arrived_ids)
    first = seen.index(True)
    assert not any(seen[:first]), "never before the last arrival"
    prompts = [p["messages"][0]["content"] for p in sent if isinstance(p, dict) and "messages" in p]
    assert sum(MARK in text for text in prompts) == 1, "the storyteller saw the ritual once"
    brief = next(text for text in prompts if MARK in text)
    assert "What is your type?" in brief and "leave the reply open for the player" in brief


def _round_trip(campaign, sid, mutate):
    """Save the live state to the database (optionally editing its JSON), forget it in memory and reload it."""
    import asyncio
    import json

    from backend.app.db.repos import SessionRepo

    pe, user = campaign.pe, "guest:ritual-tests"
    sess = pe.SESSIONS[sid]
    state = sess["state"]
    saved = json.loads(pe._serialize_state(state, sess["log"]))
    mutate(saved)
    asyncio.run(SessionRepo.create_or_update_session(
        session_id=sid, user_id=user, story_id=state.story, story_title="Six Strangers",
        player_name=state.player_name or "", gender=state.gender or "M", state_json=json.dumps(saved),
        flags_json="{}", turns=state.turns, expected_revision=int(sess.get("_db_revision") or 0)))
    del pe.SESSIONS[sid]
    return pe._try_load_session_from_db(sid, user)


def test_the_ritual_flag_survives_a_save_and_old_saves_never_replay_the_round(campaign):
    _new_game(campaign, "kept", "M")
    _briefed_turns(campaign, "kept", 16)
    assert campaign.pe.SESSIONS["kept"]["state"].opening_ritual_done is True
    reloaded = _round_trip(campaign, "kept", lambda saved: None)
    assert reloaded["state"].opening_ritual_done is True

    _new_game(campaign, "old", "M")
    assert campaign.pe.SESSIONS["old"]["state"].opening_ritual_done is False
    legacy = _round_trip(campaign, "old", lambda saved: saved.pop("opening_ritual_done"))
    assert legacy["state"].opening_ritual_done is True, "a save from before the round existed is mid-game"


def test_strangers_get_their_conduct_and_the_name_rule_beside_the_players_first_message(campaign, monkeypatch):
    """BL-76: the storyteller is told, in the per-turn header it obeys best, how well each person knows the player."""
    sent = _capture(campaign, monkeypatch)
    _new_game(campaign, "conduct", "M")
    _say(campaign, "conduct", "Oh. Hi. Um, hello.")
    calls = [p for p in sent if isinstance(p, dict) and "messages" in p]
    system, last = calls[-1]["messages"][0]["content"], calls[-1]["messages"][-1]["content"]
    assert "Bearing toward the player:" in last and "just met on camera" in last
    assert "have not heard the player's name: do not use it" in last
    assert "how well they know the player: strangers" in system, "the full conduct is in the scene section too"
    _say(campaign, "conduct", "I'm Sam, by the way.")
    calls = [p for p in sent if isinstance(p, dict) and "messages" in p]
    assert "have not heard the player's name" not in calls[-1]["messages"][-1]["content"]

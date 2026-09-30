"""BL-46 through /api/chat: a refused or unanswered ask never moves the player, a yes opens a card, not an ending.

Extraction is scripted and the storyteller is faked (fixtures from the campaign tests), so these prove the rules.
"""
import pytest

from backend.app.api.prompt_engine import _engine_move_command
from backend.app.engine.extractors.turn_extractor import SocialActUpdate, TurnExtraction
from backend.app.engine.world_model.standing import Standing

from tests.backend.app.api.test_terrace_campaigns import _new_game, _say, campaign  # noqa: F401 (fixture)


def _couple_setup(campaign, sid, standing, headers=None):
    """A new Terrace game where the player and an eligible present resident are a couple at `standing`."""
    if headers:
        campaign.client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:six_strangers|M|Sam"},
                             headers=headers)
        state = campaign.pe.SESSIONS[sid]["state"]
    else:
        state = _new_game(campaign, sid, "M")
    genders = {c["key"]: c["gender"] for c in state.story_cfg["characters"]}
    live = campaign.pe.SESSIONS[sid]["state"]
    model = live.world_model
    target = next(c for c in model.present_with_player() if genders.get(c) == "F")
    live.gender = "M"
    model.romance_relationship_partner = target
    model.standing.standings[(target, "player", "romance")] = Standing(value=standing)
    if headers:
        _save_setup(campaign, sid, "guest:" + headers["X-Guest-Id"])
    return target


def _save_setup(campaign, sid, user_id):
    """Write the in-memory setup to the database, as a saved turn would (a signed-in request reloads from it)."""
    import asyncio
    from backend.app.db.repos import SessionRepo
    sess = campaign.pe.SESSIONS[sid]
    state = sess["state"]
    sess["_db_revision"] = asyncio.run(SessionRepo.create_or_update_session(
        session_id=sid, user_id=user_id, story_id=state.story, story_title="Six Strangers",
        player_name=state.player_name or "", gender=state.gender or "M",
        state_json=campaign.pe._serialize_state(state, sess["log"]), flags_json="{}", turns=state.turns,
        expected_revision=int(sess.get("_db_revision") or 0)))


def _move_and_ask(target, destination="neighborhood"):
    return TurnExtraction(movement_intent="MOVE", destination_id=destination, confidence=0.95,
                          social_act=SocialActUpdate("ask_leave_together", target))


def _place(campaign, sid, who):
    return campaign.pe.SESSIONS[sid]["state"].world_model.world.place_of(who)


def test_a_refused_ask_does_not_move_anyone_even_if_the_extractor_guesses_a_move(campaign):
    target = _couple_setup(campaign, "refused", standing=30)          # a couple, but not ready to leave
    start = campaign.pe.SESSIONS["refused"]["state"].location_id
    campaign.script.append(_move_and_ask(target))
    body = _say(campaign, "refused", "Will you leave this house with me?")
    live = campaign.pe.SESSIONS["refused"]["state"]
    assert body["location_id"] == start == live.location_id
    assert _place(campaign, "refused", "player") == start == _place(campaign, "refused", target)
    assert "ending" not in body and "pending_choice" not in body and not live.over
    stays = [line for line in live.world_model.view.must_address if "The scene stays at" in line]
    assert stays, "the decline tells the storyteller the scene has not moved"


def test_an_outing_or_unclear_ask_moves_nobody_and_writes_no_verdict(campaign):
    target = _couple_setup(campaign, "unclear", standing=95)
    campaign.pe.SESSIONS["unclear"]["state"].world_model.romance_relationship_partner = ""   # not a couple -> unclear
    start = campaign.pe.SESSIONS["unclear"]["state"].location_id
    campaign.script.append(_move_and_ask(target))
    body = _say(campaign, "unclear", "Do you want to leave with me?")
    live = campaign.pe.SESSIONS["unclear"]["state"]
    assert body["location_id"] == start and "ending" not in body and "pending_choice" not in body
    assert live.world_model.act_cooldowns == {} and live.world_model.decision_log == []
    assert any("asks which they mean" in line for line in live.world_model.view.must_address)


def test_a_parenthesised_move_after_a_refusal_walks_the_player_alone(campaign):
    target = _couple_setup(campaign, "alone", standing=30)
    campaign.script.append(_move_and_ask(target))
    body = _say(campaign, "alone", "Will you leave this house with me? (I walk out onto the street)")
    assert body["location_id"] == "neighborhood"
    assert _place(campaign, "alone", "player") == "neighborhood"
    assert _place(campaign, "alone", target) != "neighborhood", "she said no; she does not follow"


def test_a_yes_opens_a_choice_card_and_the_player_ends_the_story_when_ready(campaign):
    target = _couple_setup(campaign, "yes", standing=95)
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("ask_leave_together", target)))
    body = _say(campaign, "yes", "Let's leave this house together, for good.")
    card = body["pending_choice"]
    assert card["id"] == "leave_together" and [o["id"] for o in card["options"]] == ["leave_now", "keep_talking"]
    assert "ending" not in body and not campaign.pe.SESSIONS["yes"]["state"].over

    keep = _say(campaign, "yes", "__choice__:leave_together:keep_talking")
    assert keep["pending_choice"] == card and "ending" not in keep, "the yes stands while they keep talking"

    final = _say(campaign, "yes", "[play ending]")
    assert final["ending"]["id"] == "left_together" and final["ending"]["kind"] == "win"
    assert "pending_choice" not in final
    assert campaign.pe.SESSIONS["yes"]["state"].world_model.pending_choice == {}
    assert any(s.get("speaker_name") == "Yukiko Ehara" for s in final["segments"]), "the judges close the run"


def test_the_card_survives_a_reload_of_the_session(campaign):
    headers = {"X-Guest-Id": "99999999-aaaa-4bbb-8ccc-dddddddddddd"}                            # anonymous sessions are never saved
    target = _couple_setup(campaign, "reload", standing=95, headers=headers)
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("ask_leave_together", target)))
    first = campaign.client.post("/api/chat", headers=headers, json={
        "session_id": "reload", "message": "Let's leave this house together, for good."}).json()
    assert first.get("pending_choice"), str(first)[:600]
    history = campaign.client.get("/api/user/sessions/reload/history", headers=headers).json()
    assert history.get("pending_choice") == first["pending_choice"], str(history)[:500]
    campaign.pe.SESSIONS.pop("reload")                                  # server restart / evicted from memory
    again = campaign.client.post("/api/chat", headers=headers, json={
        "session_id": "reload", "message": "__choice__:leave_together:leave_now"}).json()
    assert again["ending"]["id"] == "left_together"
    assert "pending_choice" not in campaign.client.get(
        "/api/user/sessions/reload/history", headers=headers).json(), "answered: no card"


@pytest.mark.parametrize("message, expected", [
    ("(I walk out onto the street)", True),
    ("Minori, leave with me? [go to the kitchen]", True),
    ("(smiles warmly) Will you leave with me?", False),
    ("(what does that mean?)", False),
    ("I walk to the kitchen", False),
])
def test_only_a_parenthesised_movement_command_counts_as_engine_move(message, expected):
    assert _engine_move_command(message) is expected


def test_an_agreed_future_plan_offers_a_skip_the_player_may_take_or_ignore(campaign):
    from backend.app.engine.extractors.turn_extractor import CommitmentUpdate
    target = _couple_setup(campaign, "plan", standing=40)
    campaign.script.append(TurnExtraction())
    assert "pending_choice" not in _say(campaign, "plan", "Hi.")
    # The extractor reads the previous exchange, so the agreed plan shows up on the next request.
    campaign.script.append(TurnExtraction(commitments=[
        CommitmentUpdate("player", target, "have a date at the cafe", "this weekend")]))
    offered = _say(campaign, "plan", "Great, it's a date then.")
    card = offered["pending_choice"]
    assert card["kind"] == "plan_skip" and "date at the cafe" in card["prompt"] and "Saturday" in card["prompt"]
    assert [o["id"] for o in card["options"]] == ["skip_to_plan", "keep_playing"]

    live = campaign.pe.SESSIONS["plan"]["state"]
    due, before = live.world_model.pending_choice["due"], live.minute
    campaign.script.append(TurnExtraction())
    skipped = _say(campaign, "plan", "__choice__:plan_skip:skip_to_plan")
    after = campaign.pe.SESSIONS["plan"]["state"]
    assert after.minute >= due > before, "the clock ran to the plan"
    assert after.world_model.pending_choice == {} and "pending_choice" not in skipped
    assert after.world_model.world.place_of(target) == after.world_model.player_place(), "they meet"


def test_a_plan_card_is_never_offered_for_something_vague_or_over_an_open_yes(campaign):
    from backend.app.engine.world_model import choices
    target = _couple_setup(campaign, "vague", standing=40)
    model = campaign.pe.SESSIONS["vague"]["state"].world_model
    memory = type("M", (), {"due": model.world.minute + 60, "owner": "player", "counterpart": target,
                            "text": "x", "agreement_id": ""})()
    from backend.app.engine.world_model.turn import _offer_skip_to_plan
    _offer_skip_to_plan(model, memory, model.world.minute)
    assert model.pending_choice == {}, "an hour away is not worth a skip"
    choices.offer_leave_together(model, target)
    memory.due = model.world.minute + 3000
    _offer_skip_to_plan(model, memory, model.world.minute)
    assert model.pending_choice["kind"] == "leave_together", "one card at a time; the bigger decision wins"

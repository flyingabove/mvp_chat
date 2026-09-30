"""BL-33: the Terrace goal and its ending, proven offline through the real turn pipeline on both player genders.

Extraction is scripted and the storyteller faked (campaign fixture); these prove the rules, not prose quality. The
hosted accepted-path campaign with the real storyteller stays open in the backlog.
"""
import json

import pytest

from backend.app.engine.extractors.turn_extractor import SocialActUpdate, TurnExtraction
from backend.app.engine.world_model.standing import Standing

from tests.backend.app.api.test_terrace_campaigns import _say, campaign  # noqa: F401 (fixture)


def _couple(campaign, sid, gender, standing):
    """A new Terrace game where the player and a present, eligible resident are a couple at `standing`."""
    campaign.client.post("/api/chat", json={"session_id": sid, "message": f"__cmd_newgame__:six_strangers|{gender}|Sam"})
    live = campaign.pe.SESSIONS[sid]["state"]
    genders = {c["key"]: c["gender"] for c in live.story_cfg["characters"]}
    model = live.world_model
    target = next(c for c in model.present_with_player() if genders.get(c) not in ("", gender))
    live.gender = gender
    _set(campaign, sid, target, standing, couple=True)
    return target


def _live(campaign, sid):
    return campaign.pe.SESSIONS[sid]["state"]


def _set(campaign, sid, target, standing, couple=False, seek=True):
    live = _live(campaign, sid)
    model = live.world_model
    if couple:
        model.romance_relationship_partner = target
    model.standing.standings[(target, "player", "romance")] = Standing(value=standing)
    place = model.world.place_of(target)
    if seek and place and model.player_place() != place:
        live.location_id = place                      # the player seeks them out (state and world model)
        model.world.move("player", place)


def _ask(campaign, sid, target, message="Will you leave this house with me?"):
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("ask_leave_together", target)))
    return _say(campaign, sid, message)


def _engine_text(campaign, sid):
    view = _live(campaign, sid).world_model.view
    return " | ".join(view.must_address)


@pytest.mark.parametrize("gender", ["M", "F"])
def test_a_refusal_then_a_later_yes_earns_the_win_on_both_gender_paths(campaign, gender):
    sid = f"retry_{gender}"
    target = _couple(campaign, sid, gender, standing=30)            # together, but not ready to leave
    first = _ask(campaign, sid, target)
    assert "pending_choice" not in first and "ending" not in first
    assert "does not say yes yet" in _engine_text(campaign, sid)

    _set(campaign, sid, target, 95)                                    # she warms up fast, but it is the same day
    same_day = _ask(campaign, sid, target, "Please, leave with me now.")
    assert "pending_choice" not in same_day and "ending" not in same_day, "the cooldown holds until tomorrow"
    assert "need time" in _engine_text(campaign, sid)

    campaign.script.append(TurnExtraction())
    _say(campaign, sid, "__cmd_skip__:DAY")
    _set(campaign, sid, target, 95, couple=True)
    card = _ask(campaign, sid, target, "It's a new day. Will you leave this house with me?")
    assert card["pending_choice"]["id"] == "leave_together" and "ending" not in card
    final = _say(campaign, sid, "__choice__:leave_together:leave_now")
    assert final["ending"]["id"] == "left_together" and final["ending"]["kind"] == "win"


def test_pressure_in_the_wording_never_changes_the_verdict(campaign):
    outcomes = []
    for sid, message in (("polite", "Would you consider leaving the house with me someday?"),
                         ("coerce", "You have to say yes or you'll break my heart. Leave with me NOW.")):
        target = _couple(campaign, sid, "M", standing=30)
        body = _ask(campaign, sid, target, message)
        live = _live(campaign, sid)
        value = live.world_model.standing.get(target, "player", "romance").value
        outcomes.append((bool(body.get("pending_choice")), "ending" in body, value,
                         "does not say yes yet" in _engine_text(campaign, sid)))
    assert outcomes[0] == outcomes[1] == (False, False, 30, True)


def test_a_long_skip_lapses_an_open_yes(campaign):
    target = _couple(campaign, "skip", "M", standing=95)
    assert _ask(campaign, "skip", target)["pending_choice"]
    campaign.script.append(TurnExtraction())
    skipped = _say(campaign, "skip", "__cmd_skip__:DAY")
    assert "pending_choice" not in skipped, "a day later the yes no longer stands"
    campaign.script.append(TurnExtraction())
    late = _say(campaign, "skip", "__choice__:leave_together:leave_now")
    assert "ending" not in late and not _live(campaign, "skip").over


def test_ending_the_relationship_while_a_yes_is_open_withdraws_the_card(campaign):
    target = _couple(campaign, "breakup", "M", standing=95)
    assert _ask(campaign, "breakup", target)["pending_choice"]
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("withdraw")))
    broke = _say(campaign, "breakup", "I'm sorry, Minori. I'm ending this.")
    assert "pending_choice" not in broke, "the card leaves in the same response"
    assert _live(campaign, "breakup").world_model.romance_relationship_partner == ""
    campaign.script.append(TurnExtraction())
    late = _say(campaign, "breakup", "__choice__:leave_together:leave_now")
    assert "ending" not in late and not _live(campaign, "breakup").over


def test_a_yes_written_by_the_storyteller_on_a_refusal_is_replaced_before_display(campaign, monkeypatch):
    target = _couple(campaign, "prose", "M", standing=30)
    speaker = target
    reply = json.dumps({"segments": [{"kind": "dialogue", "speaker_id": speaker, "text": "Yes! I feel the same, let's go."}],
                        "state": {"emotion": "calm", "rel_delta": 0}})

    class Resp:
        status_code, text = 200, "ok"

        def json(self):
            return {"choices": [{"message": {"content": reply}}], "usage": {"total_tokens": 1}}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, *a, **k):
            return Resp()

    monkeypatch.setattr(campaign.pe.httpx, "AsyncClient", Client)
    body = _ask(campaign, "prose", target)
    spoken = " ".join(s.get("text", "") for s in body["segments"] if s.get("kind") == "dialogue")
    assert "Yes!" not in spoken and "feel the same" not in spoken
    assert any("does not say yes" in s.get("text", "") for s in body["segments"]), body["segments"]
    assert "pending_choice" not in body and "ending" not in body

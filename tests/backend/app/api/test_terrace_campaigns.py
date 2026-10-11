"""BL-39 phase J: seeded month-long Terrace campaigns through the real turn pipeline.

No model calls: extraction is scripted and the storyteller is faked, so these
prove the rules (earned win, director cut, solo exit on both player-gender
paths), not prose quality.
"""
import pytest

from backend.app.engine.extractors.turn_extractor import SocialActUpdate, TurnExtraction
from tests.backend.app.api.campaign_harness import make_campaign, new_game, run_passive, run_strategic, say

_new_game, _say = new_game, say          # the old private names other campaign-based test files import


@pytest.fixture()
def campaign(monkeypatch, tmp_path):
    return make_campaign(monkeypatch, tmp_path)


def test_a_passive_player_is_eventually_cut_by_the_director(campaign):
    # A 12-roster sweep (2026-09-29) cut the passive player on days 94-135; 180 leaves margin.
    result = run_passive(campaign, "passive")
    ending = result["ending"]
    assert result["couples_left"] >= 3, f"NPC couples never left: {result['npc_couples']}"
    assert ending and ending["id"] == "cut_by_director" and ending["kind"] == "loss"


@pytest.mark.parametrize("gender", ["M", "F"])
def test_a_strategic_player_can_earn_the_win_on_both_gender_paths(campaign, gender):
    result = run_strategic(campaign, f"strategic_{gender}", gender)
    ending = result["ending"]
    assert ending and ending["id"] == "left_together",         f"no win in 40 days (confessed={result['confessed']}, standing={result['standing']})"


def test_the_player_cannot_end_the_run_by_leaving_alone(campaign):
    """BL-46: 'leave alone' is no longer a player act; only the director's clock ends a losing run."""
    new_game(campaign, "solo", "F")
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("leave_alone")))
    body = say(campaign, "solo", "I'm leaving the house alone.")
    assert "ending" not in body
    assert not campaign.pe.SESSIONS["solo"]["state"].over

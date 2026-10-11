"""BL-44 contract: the resume screen treats 404 from the history endpoint as "this saved game is gone"."""
from tests.backend.app.api.test_leave_together_api import _couple_setup, campaign  # noqa: F401 (fixture)

OWNER = {"X-Guest-Id": "aaaaaaaa-1111-4222-8333-444444444444"}
STRANGER = {"X-Guest-Id": "bbbbbbbb-1111-4222-8333-444444444444"}


def test_history_is_404_for_unknown_or_someone_elses_session_and_200_for_your_own(campaign):
    _couple_setup(campaign, "saved-game", standing=30, headers=OWNER)
    url = "/api/user/sessions/saved-game/history"
    own = campaign.client.get(url, headers=OWNER)
    assert own.status_code == 200 and "entries" in own.json()
    assert campaign.client.get(url, headers=STRANGER).status_code == 404, "another player's game looks gone"
    assert campaign.client.get("/api/user/sessions/never-existed/history", headers=OWNER).status_code == 404
    assert campaign.client.get(url).status_code == 401, "no identity is a sign-in problem, not a gone game"


def test_a_deleted_game_becomes_404(campaign):
    _couple_setup(campaign, "to-delete", standing=30, headers=OWNER)
    assert campaign.client.get("/api/user/sessions/to-delete/history", headers=OWNER).status_code == 200
    assert campaign.client.delete("/api/user/sessions/to-delete", headers=OWNER).status_code == 200
    assert campaign.client.get("/api/user/sessions/to-delete/history", headers=OWNER).status_code == 404

"""BL-29 through /api/chat: a storyteller that restates the player and invents sensations is corrected before display."""
from tests.backend.app.api.test_leave_together_api import _new_game, _say, campaign  # noqa: F401 (fixture)


def _storyteller_says(campaign, monkeypatch, text):
    class Resp:
        status_code, text_ = 200, "ok"

        def json(self):
            content = text + '\n[[STATE]]{"emotion":"calm","rel_delta":0}[[/STATE]]'
            return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 1}}

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


def test_restated_action_and_invented_sensation_never_reach_the_player(campaign, monkeypatch):
    _new_game(campaign, "slips", "M")
    _storyteller_says(campaign, monkeypatch,
                      "*Inviting her to join you in the Living Room. As you lead the way, the hallway light flickers, "
                      "making your stomach grumble.*")
    body = _say(campaign, "slips", "I invite her to join me in the living room and lead the way.")
    shown = " ".join(s.get("text", "") for s in body["segments"] if s.get("kind") == "narration")
    assert "hallway light flickers" in shown, "the new information stays"
    assert "Inviting her" not in shown and "lead the way" not in shown
    assert "stomach" not in shown

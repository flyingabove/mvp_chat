"""BL-28: a storyteller timeout must not crash the turn with HTTP 500.

`httpx.ReadTimeout` (and every other `httpx.TransportError`) used to propagate out of the chat handler as an ASGI
500 with an empty reply. Only non-2xx *responses* returned the public "story master unavailable" message.
"""
import httpx
import pytest

from tests.backend.app.api.test_terrace_campaigns import _new_game, campaign  # noqa: F401  (the scripted-turn fixture)

PUBLIC_MESSAGE = "The story master is unavailable right now"
OK_REPLY = "*ok*\n\n**\"hi\"**\n[[STATE]]{\"emotion\":\"calm\",\"rel_delta\":0}[[/STATE]]"


class _Resp:
    status_code, text = 200, "ok"

    def json(self):
        return {"choices": [{"message": {"content": OK_REPLY}}], "usage": {"total_tokens": 1}}


def _install_client(monkeypatch, pe, behaviours):
    """Replace the storyteller HTTP client. `behaviours` is consumed one call at a time: an exception is raised,
    anything else is returned as the response."""
    calls = []

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, *a, **k):
            calls.append(1)
            step = behaviours[min(len(calls), len(behaviours)) - 1]
            if isinstance(step, BaseException):
                raise step
            return step

    monkeypatch.setattr(pe.httpx, "AsyncClient", Client)
    return calls


def _chat(c, sid, message):
    return c.client.post("/api/chat", json={"session_id": sid, "message": message})


def _assistant_turns(c, sid):
    return sum(1 for m in c.pe.SESSIONS[sid]["log"] if m.get("role") == "assistant")


@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("slow"), httpx.ConnectTimeout("no route"), httpx.ConnectError("refused"),
    httpx.RemoteProtocolError("dropped"),
])
def test_a_transport_error_from_the_storyteller_is_a_retryable_message_not_a_500(campaign, monkeypatch, error):
    sid = "timeout-first-call"
    _new_game(campaign, sid, "M")
    before = _assistant_turns(campaign, sid)
    _install_client(monkeypatch, campaign.pe, [error])

    response = _chat(campaign, sid, "Hello there.")

    assert response.status_code == 200
    body = response.json()
    assert PUBLIC_MESSAGE in body["error"], body
    assert "Timeout" not in body["error"] and "httpx" not in body["error"], "no provider or transport detail leaks"
    assert _assistant_turns(campaign, sid) == before, "a failed turn adds nothing to the conversation log"


def test_the_same_message_succeeds_when_the_player_retries_after_a_timeout(campaign, monkeypatch):
    sid = "timeout-then-retry"
    _new_game(campaign, sid, "M")
    _install_client(monkeypatch, campaign.pe, [httpx.ReadTimeout("slow")])
    assert "error" in _chat(campaign, sid, "Hello there.").json()

    _install_client(monkeypatch, campaign.pe, [_Resp()])
    retry = _chat(campaign, sid, "Hello there.")

    assert retry.status_code == 200
    assert "error" not in retry.json() and retry.json()["segments"]


def test_a_timeout_during_repeat_regeneration_keeps_the_first_draft(campaign, monkeypatch):
    """The regeneration call is optional polish: losing it must not fail a turn that already has a good draft."""
    sid = "timeout-on-regeneration"
    _new_game(campaign, sid, "M")
    monkeypatch.setattr(campaign.pe, "only_repeats", lambda *a, **k: True)       # force the regeneration path
    calls = _install_client(monkeypatch, campaign.pe, [_Resp(), httpx.ReadTimeout("slow")])

    response = _chat(campaign, sid, "Hello there.")

    assert len(calls) >= 2, "the regeneration call was attempted"
    assert response.status_code == 200
    assert "error" not in response.json() and response.json()["segments"]

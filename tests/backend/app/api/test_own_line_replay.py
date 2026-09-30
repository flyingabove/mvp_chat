"""BL-47 end to end: a resident replaying a line they said many turns ago is regenerated or dropped.

Live beta 2026-09-29: Yuriko and Hikaru said their arrival introductions again, word for word, when greeted seven
turns later. The scripted storyteller below repeats a resident's old line after four other turns, which the
recent-replies filter (last three messages) cannot see.
"""
import json

from tests.backend.app.api.test_terrace_campaigns import _new_game, campaign  # noqa: F401  (the scripted-turn fixture)

OLD = "I really do like my tea with honey and a slice of lemon if there is any."
NEW = "Honestly, I could spend the whole afternoon right here talking with you."
SHORT = "Goodnight, Paul-kun. Sleep well!"


class _Resp:
    status_code, text = 200, "ok"

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": {"total_tokens": 1}}


def _reply(*beats, state="calm"):
    segments = [{"kind": "narration", "speaker_id": None, "text": text} if speaker is None else
                {"kind": "dialogue", "speaker_id": speaker, "text": text} for speaker, text in beats]
    return json.dumps({"segments": segments, "state": {"emotion": state, "rel_delta": 0}})


def _install(monkeypatch, pe, replies):
    """Serve `replies` one per storyteller call (the last repeats); returns the list of calls made."""
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
            return _Resp(replies[min(len(calls), len(replies)) - 1])

    monkeypatch.setattr(pe.httpx, "AsyncClient", Client)
    return calls


def _chat(c, sid, message):
    return c.client.post("/api/chat", json={"session_id": sid, "message": message}).json()


def _dialogue(body, speaker):
    return [seg["text"] for seg in body["segments"] if seg.get("kind") == "dialogue" and seg.get("speaker_id") == speaker]


def _fillers(who, count=4):
    return [_reply((None, "The afternoon drifts on."), (who, f"Here is a completely different thought number {i} "
                                                            f"about the house and the neighbourhood today."))
            for i in range(count)]


def _setup(campaign, monkeypatch, sid, later):
    """Game start, one turn where `who` says OLD, four different turns, then the scripted `later` replies."""
    _new_game(campaign, sid, "M")
    who = campaign.pe.SESSIONS[sid]["state"].world_model.present_with_player()[0]
    script = [_reply((who, OLD))] + _fillers(who) + [r(who) if callable(r) else r for r in later]
    calls = _install(monkeypatch, campaign.pe, script)
    for message in ("Hello there.", "And then?", "Tell me more.", "Interesting.", "I see."):
        assert "error" not in _chat(campaign, sid, message)
    return who, calls


def test_a_replayed_old_line_is_regenerated_into_a_new_one(campaign, monkeypatch):
    sid = "own-replay-regenerate"
    _new_game(campaign, sid, "M")
    who = campaign.pe.SESSIONS[sid]["state"].world_model.present_with_player()[0]
    script = [_reply((who, OLD))] + _fillers(who) + [_reply((who, OLD)), _reply((who, NEW))]
    calls = _install(monkeypatch, campaign.pe, script)
    for message in ("Hello there.", "And then?", "Tell me more.", "Interesting.", "I see."):
        _chat(campaign, sid, message)
    before = len(calls)
    assert before == 5

    body = _chat(campaign, sid, "So what do you think?")

    assert len(calls) - before == 2, "the replay triggered exactly one regeneration"
    spoken = _dialogue(body, who)
    assert NEW in spoken and OLD not in spoken, spoken


def test_a_replay_that_survives_regeneration_is_dropped_when_other_lines_remain(campaign, monkeypatch):
    sid = "own-replay-dropped"
    _new_game(campaign, sid, "M")
    who = campaign.pe.SESSIONS[sid]["state"].world_model.present_with_player()[0]
    both = _reply((who, OLD), (who, NEW))
    script = [_reply((who, OLD))] + _fillers(who) + [both, both]
    _install(monkeypatch, campaign.pe, script)
    for message in ("Hello there.", "And then?", "Tell me more.", "Interesting.", "I see."):
        _chat(campaign, sid, message)

    body = _chat(campaign, sid, "So what do you think?")

    spoken = _dialogue(body, who)
    assert NEW in spoken and OLD not in spoken, spoken


def test_a_reply_that_is_only_the_replay_is_kept_not_emptied(campaign, monkeypatch):
    sid = "own-replay-only"
    _new_game(campaign, sid, "M")
    who = campaign.pe.SESSIONS[sid]["state"].world_model.present_with_player()[0]
    script = [_reply((who, OLD))] + _fillers(who) + [_reply((who, OLD))]
    _install(monkeypatch, campaign.pe, script)
    for message in ("Hello there.", "And then?", "Tell me more.", "Interesting.", "I see."):
        _chat(campaign, sid, message)

    body = _chat(campaign, sid, "So what do you think?")

    assert "error" not in body and body["segments"], "the player never gets an empty reply"
    assert _dialogue(body, who) == [OLD]


def test_a_short_pleasantry_repeated_later_is_left_alone(campaign, monkeypatch):
    sid = "own-replay-short"
    _new_game(campaign, sid, "M")
    who = campaign.pe.SESSIONS[sid]["state"].world_model.present_with_player()[0]
    script = [_reply((who, SHORT))] + _fillers(who) + [_reply((who, SHORT), (None, "She smiles warmly."))]
    calls = _install(monkeypatch, campaign.pe, script)
    for message in ("Hello there.", "And then?", "Tell me more.", "Interesting.", "I see."):
        _chat(campaign, sid, message)
    before = len(calls)

    body = _chat(campaign, sid, "You are lovely.")

    assert len(calls) - before == 1, "no regeneration for a short line"
    assert SHORT in _dialogue(body, who)


def test_a_new_line_needs_no_regeneration(campaign, monkeypatch):
    sid = "own-replay-none"
    _new_game(campaign, sid, "M")
    who = campaign.pe.SESSIONS[sid]["state"].world_model.present_with_player()[0]
    script = [_reply((who, OLD))] + _fillers(who) + [_reply((who, NEW))]
    calls = _install(monkeypatch, campaign.pe, script)
    for message in ("Hello there.", "And then?", "Tell me more.", "Interesting.", "I see."):
        _chat(campaign, sid, message)
    before = len(calls)

    body = _chat(campaign, sid, "So what do you think?")

    assert len(calls) - before == 1
    assert _dialogue(body, who) == [NEW]

"""BL-33: the hosted Terrace campaign driver, proven offline against a fake server (no network, no cost)."""
import pytest

from scripts.verify_terrace_win_hosted import (
    ASK, CONFESS, WARM, Campaign, load_cast, pick_message, pick_target, rival_evidence, speakers, together,
)

CAST = load_cast()


def _say(who, text="hello"):
    return {"kind": "dialogue", "speaker_id": who, "speaker_name": who.title(), "text": text}


class FakeServer:
    """A tiny stand-in for the game: the target is in another room until the player goes looking, becomes a couple
    when confessed to after day 3, and says yes to the ask the day after."""

    def __init__(self, target, accepts=True):
        self.target, self.accepts = target, accepts
        self.day, self.here, self.couple_day, self.messages = 0, False, None, []

    def body(self, segments, **extra):
        goal = {"text": "goal", "status": f"You and {self.target.title()} are together. Now you both need to choose to leave."
                if self.couple_day is not None else "No mutual relationship yet."}
        return {"reply": "x", "segments": segments, "goal": goal, **extra}

    def __call__(self, message, **extra):
        self.messages.append(message)
        if message.startswith("__cmd_skip__"):
            self.day += 1
            self.here = False
            return 200, self.body([{"kind": "narration", "text": "A day passes."}])
        if message.startswith("__choice__:leave_together:leave_now"):
            return 200, self.body([_say("yukiko")], ending={"id": "left_together", "kind": "win"})
        if message.startswith("I go to the"):
            self.here = "kitchen" in message
            return 200, self.body([{"kind": "narration", "text": "You walk."}])
        if "feelings for you" in message or "be together" in message:
            if self.accepts and self.day >= 3 and self.here:
                self.couple_day = self.day
            return 200, self.body([_say(self.target)] if self.here else [_say("someone_else")])
        if "leave" in message and self.couple_day is not None and self.day > self.couple_day:
            return 200, self.body([_say(self.target)], pending_choice={"id": "leave_together"})
        return 200, self.body([_say(self.target)] if self.here else [_say("someone_else")])


def _campaign(server, gender, **kwargs):
    return Campaign(server, gender, CAST, log=lambda line: None, **kwargs)


@pytest.mark.parametrize("gender, target", [("M", "minori"), ("F", "makoto")])
def test_the_driver_earns_the_win_on_both_gender_paths(gender, target):
    server = FakeServer(target)
    server.here = True                                    # the target is in the room at the start
    result = _campaign(server, gender, max_days=20, max_turns=200).run()
    assert result["won"] and result["ending"]["id"] == "left_together"
    assert result["target"] == target and result["together_day"] is not None
    assert result["days"] < 20


def test_it_goes_looking_when_the_target_is_not_in_the_room():
    server = FakeServer("minori")
    result = _campaign(server, "M", max_days=20, max_turns=300).run()
    assert any(m.startswith("I go to the") for m in server.messages), "it searched the rooms"
    assert result["won"]


def test_the_caps_bound_the_cost_when_the_answer_is_always_no():
    by_days = _campaign(FakeServer("minori", accepts=False), "M", max_days=6, max_turns=500).run()
    assert not by_days["won"] and by_days["days"] <= 6 and by_days["turns"] < 500
    by_turns = _campaign(FakeServer("minori", accepts=False), "M", max_days=100, max_turns=15).run()
    assert not by_turns["won"] and by_turns["turns"] <= 15


def test_the_same_line_is_never_sent_twice_in_a_row():
    server = FakeServer("minori")
    server.here = True
    _campaign(server, "M", max_days=12, max_turns=200).run()
    talk = [m for m in server.messages if not m.startswith("__")]
    assert all(a != b for a, b in zip(talk, talk[1:]))
    assert pick_message(WARM, "Minori", 0, last=WARM[0].format(n="Minori")) != WARM[0].format(n="Minori")
    assert pick_message(("only one {n}",), "Ann", 0, last="only one Ann") == "only one Ann", "a one-line pool still works"


def test_targets_are_opposite_gender_and_stick():
    assert pick_target({"makoto", "yuki", "minori"}, CAST, "M") == "minori"
    assert pick_target({"makoto", "minori"}, CAST, "F") == "makoto"
    assert pick_target({"makoto", "yuki"}, CAST, "M") == "", "no one of the other gender seen yet"
    assert pick_target({"mizuki"}, CAST, "M", current="minori") == "minori"
    assert pick_target({"nobody_known"}, CAST, "M") == ""


def test_status_and_speaker_parsing():
    assert together({"goal": {"status": "You and Minori are together. Now you both need to choose to leave."}})
    assert not together({"goal": {"status": "No mutual relationship yet."}}) and not together({})
    body = {"segments": [{"kind": "dialogue", "speaker_id": "minori"}, {"kind": "narration", "speaker_id": None},
                         {"kind": "dialogue", "speaker_id": None}]}
    assert speakers(body) == {"minori"}


def test_rival_evidence_picks_out_a_same_gender_residents_invitation():
    body = {"segments": [{"kind": "narration", "text": "Makoto invited Minori to spend time together tomorrow evening."},
                         {"kind": "narration", "text": "Minori invited you to sit down."},
                         {"kind": "dialogue", "speaker_id": "yuki", "text": "Nice weather."}]}
    found = rival_evidence(body, CAST, "M")
    assert len(found) == 1 and "Makoto" in found[0]
    assert rival_evidence(body, CAST, "F") == [body["segments"][1]["text"]], "for a female player Minori is the rival"
    assert ASK and CONFESS and len(WARM) >= 8

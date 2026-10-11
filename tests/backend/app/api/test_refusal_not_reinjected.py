"""BL-47 part 2 through /api/chat: a refusal is voiced on the turn of the ask, not replayed on unrelated turns."""
from backend.app.engine.extractors.turn_extractor import SocialActUpdate, TurnExtraction

from tests.backend.app.api.test_leave_together_api import _couple_setup, _say, campaign  # noqa: F401 (fixture)


def _engine_text(campaign, sid):
    """Everything the engine told the storyteller this turn about the scene, as one string."""
    view = campaign.pe.SESSIONS[sid]["state"].world_model.view
    remembered = [line for items in view.perspectives.values() for line in items]
    return " | ".join(list(view.must_address) + remembered)


def test_the_refusal_directive_is_only_on_the_turn_of_the_ask(campaign):
    target = _couple_setup(campaign, "reused", standing=30)                # a couple, not ready to leave
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("ask_leave_together", target)))
    _say(campaign, "reused", "Will you leave this house with me?")
    assert "does not say yes yet" in _engine_text(campaign, "reused"), "the ask turn carries the verdict"

    model = campaign.pe.SESSIONS["reused"]["state"].world_model     # a turn publishes a fresh state: re-fetch
    # She voiced the refusal; the game keeps it as a spoken-line memory for her and for whoever heard it.
    line = f"@{target} said: I want to take my time getting to know everyone, no big plans for now."
    listeners = [c for c in model.present_with_player() if c != target] + [target]
    for cid in listeners:
        model.memories.add(cid, line, "witnessed", model.world.minute, kind="dialogue")

    name = model.characters[target].name.split()[0]
    for message in (f"{name}, can I make you some breakfast?", f"{name}, want to move to the living room?",
                    f"{name}, what do you think of the weather?"):
        campaign.script.append(TurnExtraction())
        _say(campaign, "reused", message)
        text = _engine_text(campaign, "reused")
        assert "does not say yes" not in text and "turns it down" not in text, message
        assert "take my time" not in text and "no big plans" not in text, message


def test_a_25_turn_replay_never_serves_the_refusal_back(campaign):
    """Measure: turns (of 25 plain, name-addressing messages after one refusal) whose engine text carries the line.
    Before the fix this was every turn the player named her; it must now be 0."""
    target = _couple_setup(campaign, "replay25", standing=30)
    campaign.script.append(TurnExtraction(social_act=SocialActUpdate("ask_leave_together", target)))
    _say(campaign, "replay25", "Will you leave this house with me?")
    model = campaign.pe.SESSIONS["replay25"]["state"].world_model
    name = model.characters[target].name.split()[0]
    for cid in model.present_with_player():
        model.memories.add(cid, f"@{target} said: I want to take my time getting to know everyone, no big plans for now.",
                           "witnessed", model.world.minute, kind="dialogue")
    topics = ["the tea", "the weather", "the garden", "your day", "the news", "dinner", "the music", "the sofa",
              "your book"]
    repeats = 0
    for turn in range(25):
        campaign.script.append(TurnExtraction())
        _say(campaign, "replay25", f"{name}, what do you think about {topics[turn % len(topics)]}?")
        repeats += "take my time" in _engine_text(campaign, "replay25")
    assert repeats == 0, f"the refusal came back on {repeats} of 25 turns"

"""BL-34 through the real bootstrap: in a new Terrace game every rival already has an aim of their own."""
import pytest

from backend.app.engine.extractors.turn_extractor import TurnExtraction
from backend.app.engine.world_model.agenda import intentions

from tests.backend.app.api.test_terrace_campaigns import _say, campaign  # noqa: F401 (fixture)


@pytest.mark.parametrize("gender", ["M", "F"])
def test_every_same_gender_resident_starts_with_an_aim_on_an_opposite_gender_resident(campaign, gender):
    sid = f"aims_{gender}"
    campaign.client.post("/api/chat", json={"session_id": sid, "message": f"__cmd_newgame__:six_strangers|{gender}|Sam"})
    campaign.script.append(TurnExtraction())
    _say(campaign, sid, "Hello, everyone.")
    state = campaign.pe.SESSIONS[sid]["state"]
    model = state.world_model
    genders = {c["key"]: c["gender"] for c in state.story_cfg["characters"]}
    rivals = [c for c in model.characters if genders.get(c) == gender]
    assert rivals, "the house has same-gender residents"
    for rival in rivals:
        aims = [i for i in intentions(model, rival, model.world.day_index(model.world.minute)) if i.kind == "pursue"]
        assert aims, f"{rival} has no aim of their own"
        assert all(genders[i.target] != gender and i.target in model.characters for i in aims)

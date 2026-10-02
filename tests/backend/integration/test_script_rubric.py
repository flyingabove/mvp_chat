"""Agreement gate for the Jev script rubric against the owner's labels, against LIVE Jev.

Never runs on deployment: `@pytest.mark.integration`, deselected by the Docker gate and the CI unit job. Run by hand
(it calls live Jev, which is free):

    pytest -m integration tests/backend/integration/test_script_rubric.py -s

Until `rubric.LABELS_REQUIRED` scenes are labelled (tests/eval_cases/script_rubric/README.md) the rubric is advisory:
this test then asserts exactly that, and makes no Jev call. Once enough are labelled it enforces the stated bar on the
held-out set, then on the dev set.
"""
import pytest

from backend.app.sim import rubric
from scripts.eval import script_rubric_eval as ev


@pytest.fixture()
def live_jev(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "TYPESAFE_ENABLED", True)
    rubric.reset_resolver_for_tests()
    yield
    rubric.reset_resolver_for_tests()


@pytest.mark.integration
def test_the_rubric_is_advisory_until_enough_scenes_are_labelled_then_meets_the_bar(live_jev, capsys):
    ready = ev.labelled(ev.load("all"))
    if len(ready) < rubric.LABELS_REQUIRED:
        assert rubric.CALIBRATED is False, "calibrated without the labelled scenes that justify it"
        return
    import asyncio

    async def judge_both() -> dict:
        # One event loop for both sets: the shared httpx client is bound to the loop that first used it.
        return {name: await ev.judge_cases(ev.labelled(ev.load(name))) for name in ("holdout", "dev")}

    results = asyncio.run(judge_both())
    for name in ("holdout", "dev"):
        cases = ev.labelled(ev.load(name))
        agreement = ev.tally(cases, results[name])
        with capsys.disabled():
            ev.report(agreement, name)
        assert agreement.unanswered == 0, "Jev left rubric items unanswered; check TYPESAFE_API_KEY and the breaker"
        assert agreement.passes(), f"rubric agreement with the owner's labels is below the bar on '{name}'"

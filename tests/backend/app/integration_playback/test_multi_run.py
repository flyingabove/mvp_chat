"""Unit tests for the multi-run scoring infrastructure in IntegrationScenario."""
from __future__ import annotations


# ---------------------------------------------------------------------------
# _integ_run_count — local vs prod detection
# ---------------------------------------------------------------------------

def test_integ_run_count_local(monkeypatch):
    """Without Railway env vars, _integ_run_count() returns LOCAL_INTEG_RUN_COUNT."""
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)

    from backend.app.integration_playback.scenario import _integ_run_count
    from backend.app.config.settings import LOCAL_INTEG_RUN_COUNT

    result = _integ_run_count()
    assert isinstance(result, int)
    assert result > 0
    assert result == LOCAL_INTEG_RUN_COUNT


def test_integ_run_count_prod_via_railway_environment(monkeypatch):
    """With RAILWAY_ENVIRONMENT set, _integ_run_count() returns PROD_INTEG_RUN_COUNT."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)

    from backend.app.integration_playback.scenario import _integ_run_count
    from backend.app.config.settings import PROD_INTEG_RUN_COUNT

    result = _integ_run_count()
    assert isinstance(result, int)
    assert result > 0
    assert result == PROD_INTEG_RUN_COUNT


def test_integ_run_count_prod_via_railway_project_id(monkeypatch):
    """With RAILWAY_PROJECT_ID set, _integ_run_count() returns PROD_INTEG_RUN_COUNT."""
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj-abc123")

    from backend.app.integration_playback.scenario import _integ_run_count
    from backend.app.config.settings import PROD_INTEG_RUN_COUNT

    result = _integ_run_count()
    assert result == PROD_INTEG_RUN_COUNT


# ---------------------------------------------------------------------------
# record_score / _score_history class-level accumulation
# ---------------------------------------------------------------------------

def test_record_score_accumulates_on_class():
    """record_score() appends to the class-level _score_history list."""
    from backend.app.integration_playback.scenario import IntegrationScenario

    class _DummyScenario(IntegrationScenario):
        scenario_id = ""  # empty prevents auto-registration
        title = "dummy"
        description = ""
        tags = []

    _DummyScenario._score_history = []
    instance = _DummyScenario()
    instance.record_score(100)
    instance.record_score(50)
    instance.record_score(0)

    assert _DummyScenario._score_history == [100, 50, 0]


def test_score_history_is_per_class_not_shared():
    """Each subclass has its own _score_history — not shared with siblings."""
    from backend.app.integration_playback.scenario import IntegrationScenario

    class _Alpha(IntegrationScenario):
        scenario_id = ""
        title = "alpha"
        description = ""
        tags = []

    class _Beta(IntegrationScenario):
        scenario_id = ""
        title = "beta_dummy"
        description = ""
        tags = []

    _Alpha._score_history = []
    _Beta._score_history = []

    _Alpha().record_score(100)
    _Beta().record_score(50)

    assert _Alpha._score_history == [100]
    assert _Beta._score_history == [50]

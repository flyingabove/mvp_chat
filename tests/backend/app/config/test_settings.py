from backend.app.config import settings


def test_settings_have_expected_defaults():
    # These defaults are relied upon by gameplay + prompt building.
    assert isinstance(settings.OPENAI_API_KEY, str)
    assert settings.OPENAI_MODEL
    assert settings.MEMORY_TURNS > 0
    assert settings.MAX_TOKENS > 0
    assert 0 <= settings.TEMPERATURE <= 2

    assert settings.START_LOCATION
    assert settings.TRAVEL_MINS >= 0


def test_extractor_turns_exists_and_is_positive():
    """EXTRACTOR_TURNS controls conversation history sent to location extractor."""
    assert hasattr(settings, "EXTRACTOR_TURNS")
    assert settings.EXTRACTOR_TURNS > 0
    assert isinstance(settings.EXTRACTOR_TURNS, int)


def test_local_integ_run_count_is_positive_int():
    """LOCAL_INTEG_RUN_COUNT (X) must exist and be a positive integer."""
    assert hasattr(settings, "LOCAL_INTEG_RUN_COUNT")
    assert isinstance(settings.LOCAL_INTEG_RUN_COUNT, int)
    assert settings.LOCAL_INTEG_RUN_COUNT > 0


def test_prod_integ_run_count_is_positive_int():
    """PROD_INTEG_RUN_COUNT (Y) must exist and be a positive integer."""
    assert hasattr(settings, "PROD_INTEG_RUN_COUNT")
    assert isinstance(settings.PROD_INTEG_RUN_COUNT, int)
    assert settings.PROD_INTEG_RUN_COUNT > 0

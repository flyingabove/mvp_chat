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

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

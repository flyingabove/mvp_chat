"""BL-79: unit tests never talk to Jev, whatever this machine's `.env.test` says.

A developer machine with TYPESAFE_API_KEY / TYPESAFE_ENABLED set made every turn in a unit test make a second (Jev)
HTTP post and broke call-count tests. `tests/conftest.py` pins Jev off for every test that is not marked
`integration`; integration tests keep the real settings.
"""
import pytest

from backend.app.config import settings
from backend.app.config.credentials import get_typesafe_api_key, is_typesafe_enabled


def test_unit_tests_run_with_jev_off():
    assert settings.TYPESAFE_ENABLED is False
    assert settings.TYPESAFE_API_KEY == ""


@pytest.mark.integration
def test_integration_tests_keep_the_real_jev_settings():
    assert settings.TYPESAFE_ENABLED == is_typesafe_enabled()
    assert settings.TYPESAFE_API_KEY == get_typesafe_api_key()

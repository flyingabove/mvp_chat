"""Unit tests for credential helpers that load .env.test as a fallback.

Covers: live-env wins, .env.test fallback, case-only key tolerance, JWT default.
"""
import os
import textwrap

import pytest

import backend.app.config.credentials as credentials


@pytest.fixture(autouse=True)
def _reset_loader_guard(monkeypatch):
    """Each test starts with the .env.test loader guard reset so re-entry is testable."""
    monkeypatch.setattr(credentials, "_env_test_loaded", False, raising=True)
    yield


def test_get_google_client_id_prefers_live_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "  live-client-id  ")
    assert credentials.get_google_client_id() == "live-client-id"


def test_get_google_client_secret_prefers_live_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "  live-secret  ")
    assert credentials.get_google_client_secret() == "live-secret"


def test_get_jwt_secret_prefers_live_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "  live-jwt-secret  ")
    assert credentials.get_jwt_secret() == "live-jwt-secret"


def test_get_jwt_secret_falls_back_to_dev_sentinel(monkeypatch, tmp_path):
    """When nothing is set anywhere, JWT helper returns the documented dev sentinel."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.get_jwt_secret() == "dev-secret-change-in-production"


def test_falls_back_to_env_test_when_live_env_missing(monkeypatch, tmp_path):
    """If a value is absent from os.environ but present in .env.test, the helper picks it up."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    (tmp_path / ".env.test").write_text(
        textwrap.dedent(
            """
            # comment line
            GOOGLE_CLIENT_ID=loaded-from-file
            GOOGLE_CLIENT_SECRET="quoted-secret"
            JWT_SECRET=loaded-jwt
            """
        ).strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)

    try:
        assert credentials.get_google_client_id() == "loaded-from-file"
        assert credentials.get_google_client_secret() == "quoted-secret"
        assert credentials.get_jwt_secret() == "loaded-jwt"
    finally:
        # Don't leak loader-side env writes into other tests.
        for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "JWT_SECRET"):
            os.environ.pop(key, None)


def test_get_env_with_fallback_tolerates_case_mismatch(monkeypatch, tmp_path):
    """Some host dashboards lowercase the key; the helper should still match it."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    os.environ["google_client_id"] = "case-only"
    try:
        assert credentials.get_google_client_id() == "case-only"
    finally:
        os.environ.pop("google_client_id", None)


def test_get_env_with_fallback_ignores_whitespace_keys(monkeypatch, tmp_path):
    """A whitespace-padded env key must not be accepted as a match."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    os.environ["GOOGLE_CLIENT_ID "] = "padded"
    try:
        assert credentials.get_google_client_id() == ""
    finally:
        os.environ.pop("GOOGLE_CLIENT_ID ", None)


# --- LangSmith tracing credentials -------------------------------------------
# Tracing is opt-in: holding the key must never by itself start shipping player
# content to an external service, so is_langsmith_enabled() requires the flag.

def test_get_langsmith_api_key_prefers_live_env(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "  lsv2_live  ")
    assert credentials.get_langsmith_api_key() == "lsv2_live"


def test_get_langsmith_api_key_falls_back_to_env_test(monkeypatch, tmp_path):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    (tmp_path / ".env.test").write_text("LANGSMITH_API_KEY=lsv2_from_file", encoding="utf-8")
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    try:
        assert credentials.get_langsmith_api_key() == "lsv2_from_file"
    finally:
        os.environ.pop("LANGSMITH_API_KEY", None)


def test_get_langsmith_api_key_empty_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.get_langsmith_api_key() == ""


def test_get_langsmith_project_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.get_langsmith_project() == "storieschat"


def test_get_langsmith_project_prefers_live_env(monkeypatch):
    monkeypatch.setenv("LANGSMITH_PROJECT", "storieschat-prod")
    assert credentials.get_langsmith_project() == "storieschat-prod"


def test_langsmith_disabled_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_langsmith_enabled() is False


def test_langsmith_disabled_when_key_present_but_flag_unset(monkeypatch, tmp_path):
    """Regression guard: a populated .env.test key must not auto-enable tracing."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_present")
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_langsmith_enabled() is False


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_langsmith_enabled_for_truthy_flags(monkeypatch, tmp_path, flag):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_present")
    monkeypatch.setenv("LANGSMITH_TRACING", flag)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_langsmith_enabled() is True


@pytest.mark.parametrize("flag", ["0", "false", "no", "off", "", "maybe"])
def test_langsmith_disabled_for_falsy_flags(monkeypatch, tmp_path, flag):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_present")
    monkeypatch.setenv("LANGSMITH_TRACING", flag)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_langsmith_enabled() is False


# --- TypeSafe AI / Jev credentials -------------------------------------------
# Same opt-in design as LangSmith above: holding the key must never by itself
# start routing real decisions through a third-party model.

def test_get_typesafe_api_key_prefers_live_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "  apikey_live  ")
    assert credentials.get_typesafe_api_key() == "apikey_live"


def test_get_typesafe_api_key_falls_back_to_env_test(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    (tmp_path / ".env.test").write_text("TYPESAFE_API_KEY=apikey_from_file", encoding="utf-8")
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    try:
        assert credentials.get_typesafe_api_key() == "apikey_from_file"
    finally:
        os.environ.pop("TYPESAFE_API_KEY", None)


def test_get_typesafe_api_key_empty_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.get_typesafe_api_key() == ""


def test_get_typesafe_model_defaults_to_jev_latest(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_MODEL", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.get_typesafe_model() == "jev-latest"


def test_get_typesafe_model_prefers_pinned_version(monkeypatch):
    """Pinning a specific version (not the moving 'jev-latest' alias) is the
    documented safe path once threshold-tuned production use begins."""
    monkeypatch.setenv("TYPESAFE_MODEL", "jev-1.13.0")
    assert credentials.get_typesafe_model() == "jev-1.13.0"


def test_typesafe_disabled_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_ENABLED", "true")
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_typesafe_enabled() is False


def test_typesafe_disabled_when_key_present_but_flag_unset(monkeypatch, tmp_path):
    """Regression guard: a populated .env.test key must not auto-enable Jev routing."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_present")
    monkeypatch.delenv("TYPESAFE_ENABLED", raising=False)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_typesafe_enabled() is False


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_typesafe_enabled_for_truthy_flags(monkeypatch, tmp_path, flag):
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_present")
    monkeypatch.setenv("TYPESAFE_ENABLED", flag)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_typesafe_enabled() is True


@pytest.mark.parametrize("flag", ["0", "false", "no", "off", "", "maybe"])
def test_typesafe_disabled_for_falsy_flags(monkeypatch, tmp_path, flag):
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_present")
    monkeypatch.setenv("TYPESAFE_ENABLED", flag)
    monkeypatch.setattr(credentials, "_find_project_root", lambda: tmp_path)
    assert credentials.is_typesafe_enabled() is False

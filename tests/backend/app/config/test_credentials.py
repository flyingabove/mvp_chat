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

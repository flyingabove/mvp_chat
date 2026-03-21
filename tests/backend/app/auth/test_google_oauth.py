"""Unit tests for Google OAuth env resolution helpers."""

import os

import backend.app.auth.google_oauth as google_oauth


def test_resolved_google_client_secret_prefers_live_env(monkeypatch):
    """Resolver should read current env, not only module-level import values."""
    monkeypatch.setattr(google_oauth, "GOOGLE_CLIENT_SECRET", "", raising=True)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "  live-secret  ")

    assert google_oauth._resolved_google_client_secret() == "live-secret"


def test_resolved_google_client_secret_accepts_case_mismatch(monkeypatch):
    """Resolver should tolerate case-only key mismatches from host dashboards."""
    monkeypatch.setattr(google_oauth, "GOOGLE_CLIENT_SECRET", "", raising=True)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    os.environ["google_client_secret"] = "case-secret"
    try:
        assert google_oauth._resolved_google_client_secret() == "case-secret"
    finally:
        os.environ.pop("google_client_secret", None)


def test_resolved_google_client_secret_falls_back_to_settings(monkeypatch):
    """When env is absent, fallback to settings-imported constant remains intact."""
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    os.environ.pop("google_client_secret", None)
    monkeypatch.setattr(google_oauth, "GOOGLE_CLIENT_SECRET", "settings-secret", raising=True)

    assert google_oauth._resolved_google_client_secret() == "settings-secret"


def test_resolved_google_client_secret_ignores_trailing_space_key(monkeypatch):
    """Resolver must not accept whitespace-padded env var keys."""
    monkeypatch.setattr(google_oauth, "GOOGLE_CLIENT_SECRET", "", raising=True)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    os.environ["GOOGLE_CLIENT_SECRET "] = "bad-secret"
    try:
        assert google_oauth._resolved_google_client_secret() == ""
    finally:
        os.environ.pop("GOOGLE_CLIENT_SECRET ", None)

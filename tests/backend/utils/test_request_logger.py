import os


def test_request_logger_respects_env_toggle(monkeypatch, capsys):
    from app.utils.request_logger import log_event

    monkeypatch.setenv("REQUEST_LOGGING", "0")
    log_event("rid", "stage", {"a": 1})
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("REQUEST_LOGGING", "1")
    log_event("rid", "stage", {"a": 1})
    out = capsys.readouterr().out
    assert "\"request_id\"" in out and "\"stage\"" in out
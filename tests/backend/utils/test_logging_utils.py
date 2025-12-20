from app.utils.logging import jlog, truncate


def test_truncate_behavior():
    assert truncate("abc", 2).startswith("a")
    assert truncate("", 10) == ""


def test_jlog_prints_json(capsys):
    jlog({"kind": "x"})
    out = capsys.readouterr().out.strip()
    assert out.startswith("{") and "\"kind\"" in out


def test_request_logger_can_disable(monkeypatch, capsys):
    from app.utils.request_logger import log_event

    monkeypatch.setenv("REQUEST_LOGGING", "0")
    log_event("rid", "stage", {"x": 1})
    out = capsys.readouterr().out.strip()
    assert out == ""


def test_request_logger_emits_when_enabled(monkeypatch, capsys):
    from app.utils.request_logger import log_event

    monkeypatch.setenv("REQUEST_LOGGING", "1")
    log_event("rid", "stage", {"x": 1})
    out = capsys.readouterr().out.strip()
    assert "\"request_id\"" in out
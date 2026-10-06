"""Operator-only Drama Theatre routes and page (BL-86, P-13)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api import theatre as api
from backend.app.sim import theatre as theatre_module
from backend.app.sim.writer import FakeWriter

BASE = "/beta/debug/theatre"


@pytest.fixture
def client(monkeypatch, tmp_path):
    from backend.app.main import app
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "s3cret")
    monkeypatch.setattr(api, "WRITER_FACTORY", lambda loop: (lambda setup, cap: FakeWriter()))
    monkeypatch.setattr(theatre_module, "LOG_DIR", tmp_path)
    monkeypatch.setattr("backend.app.sim.theatre.LOG_DIR", tmp_path)
    api.SESSIONS.clear()
    c = TestClient(app)
    c.headers.update({"X-Operator-Token": "s3cret"})
    yield c
    api.SESSIONS.clear()


def _start(client, **body):
    response = client.post(f"{BASE}/start", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_every_route_needs_the_operator_token(monkeypatch):
    from backend.app.main import app
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "s3cret")
    anon = TestClient(app)
    for method, path in (("post", "/start"), ("get", "/sessions"), ("get", "/replay/x"), ("get", "/abc"),
                         ("post", "/abc/step"), ("post", "/abc/say")):
        assert getattr(anon, method)(BASE + path).status_code in (401, 403), path
    assert anon.post(BASE + "/start", headers={"X-Operator-Token": "wrong"}).status_code == 401


def test_start_step_say_and_poll_a_session(client):
    state = _start(client)
    sid = state["id"]
    assert len(state["cast"]) == 6 and state["beats"] == [] and state["story"]
    after = client.post(f"{BASE}/{sid}/step?since=0").json()
    assert [b["type"] for b in after["beats"]] == ["scene"] and after["last"] == 1 and after["calls"] >= 1
    said = client.post(f"{BASE}/{sid}/say?since=1", json={"text": "skip to evening"}).json()
    assert [b["type"] for b in said["beats"]] == ["skip"] and said["clock"].endswith("19:00")
    nudged = client.post(f"{BASE}/{sid}/say?since=2", json={"text": "Makoto finds a note", "then_step": True}).json()
    assert [b["type"] for b in nudged["beats"]] == ["nudge", "scene"] and nudged["beats"][1]["nudged"] == ["Makoto finds a note"]
    polled = client.get(f"{BASE}/{sid}?since=3").json()
    assert polled["last"] == 4 and [b["n"] for b in polled["beats"]] == [4]


def test_unknown_session_story_and_empty_nudge_get_plain_errors(client):
    assert client.post(f"{BASE}/nope/step").status_code == 404
    assert client.post(f"{BASE}/start", json={"story": "no_such_story"}).status_code == 404
    sid = _start(client)["id"]
    assert client.post(f"{BASE}/{sid}/say", json={"text": "   "}).status_code == 422, "blank text is refused"


def test_the_call_cap_is_a_409_not_a_crash(client):
    sid = _start(client, call_cap=2)["id"]
    assert client.post(f"{BASE}/{sid}/step").status_code == 200
    response = client.post(f"{BASE}/{sid}/step")
    assert response.status_code == 409 and "model calls" in response.json()["detail"]


def test_a_model_failure_is_a_502_with_words_and_the_session_survives(client, monkeypatch):
    sid = _start(client)["id"]
    writer = api.SESSIONS[sid].theatre.writer
    original = writer.write_scene
    state = {"fail": True}

    def flaky(prompt):
        if state["fail"]:
            state["fail"] = False
            raise RuntimeError("model down")
        return original(prompt)
    monkeypatch.setattr(writer, "write_scene", flaky)
    response = client.post(f"{BASE}/{sid}/step")
    assert response.status_code == 502 and "try again" in response.json()["detail"]
    assert client.post(f"{BASE}/{sid}/step").status_code == 200


def test_sessions_list_and_replay_come_from_the_saved_log(client):
    sid = _start(client)["id"]
    client.post(f"{BASE}/{sid}/step")
    listing = client.get(f"{BASE}/sessions").json()
    assert listing["live"][0]["id"] == sid and listing["saved"][0]["id"] == sid and listing["saved"][0]["scenes"] == 1
    replay = client.get(f"{BASE}/replay/{sid}").json()
    assert [b["type"] for b in replay["beats"]] == ["scene"]
    assert client.get(f"{BASE}/replay/missing").status_code == 404
    assert client.get(f"{BASE}/replay/..%2F..%2Fetc").status_code in (400, 404)


def test_only_a_few_sessions_are_kept(client):
    ids = [_start(client)["id"] for _ in range(api.MAX_SESSIONS + 2)]
    assert len(api.SESSIONS) == api.MAX_SESSIONS and ids[-1] in api.SESSIONS and ids[0] not in api.SESSIONS


def test_the_real_writer_is_refused_when_it_would_run_on_openai(monkeypatch):
    from backend.app.main import app
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "s3cret")
    monkeypatch.setattr(api, "WRITER_FACTORY", api._real_writer_factory)
    monkeypatch.setattr(api, "_provider", lambda: "openai")
    response = TestClient(app).post(BASE + "/start", json={}, headers={"X-Operator-Token": "s3cret"})
    assert response.status_code == 409 and "OpenAI" in response.json()["detail"]


def test_the_page_is_served_and_holds_no_data():
    from backend.app.main import app
    for path in ("/drama", "/beta/drama"):
        response = TestClient(app).get(path)
        assert response.status_code == 200 and "Drama Theatre" in response.text and "/beta/debug/theatre" in response.text
        assert "s3cret" not in response.text

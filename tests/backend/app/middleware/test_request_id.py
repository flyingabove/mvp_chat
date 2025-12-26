from fastapi.testclient import TestClient


def test_request_id_middleware_passthrough_and_generation(monkeypatch):
    from backend.app import main

    client = TestClient(main.app)

    # Provided request id should be echoed back
    r = client.get("/api/version", headers={"X-Request-ID": "abc123"})
    assert r.headers.get("X-Request-ID") == "abc123"

    # Missing request id should be generated
    r2 = client.get("/api/version")
    assert r2.headers.get("X-Request-ID")
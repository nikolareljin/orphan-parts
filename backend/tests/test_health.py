from fastapi.testclient import TestClient


def test_healthz_answers_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_reports_fixture_mode_and_writable_data_dir(client: TestClient) -> None:
    body = client.get("/readyz").json()
    assert body["status"] == "ok"
    assert body["model_api"] == "fixture"
    assert body["data_dir_writable"] is True


def test_version_lists_every_model_id(client: TestClient) -> None:
    body = client.get("/api/version").json()
    assert body["version"] == "0.1.0"
    assert set(body["models"]) == {"spark", "wonder", "image", "voice", "sam"}
    assert body["models"]["sam"] == "sam-3.1"


def test_every_response_carries_request_id_and_security_headers(client: TestClient) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    rid = client.get("/healthz").headers["X-Request-ID"]
    assert len(rid) == 16


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    ok = client.options(
        "/healthz",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options(
        "/healthz",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import __version__
from app.api.routes import _writable
from app.config import Settings
from app.main import create_app


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
    assert body["version"] == __version__
    assert set(body["models"]) == {"spark", "wonder", "image", "voice", "sam"}
    assert body["models"]["sam"] == "sam-3.1"


def test_version_reports_the_upload_limits(client: TestClient, settings: Settings) -> None:
    body = client.get("/api/version").json()
    assert body["limits"] == {
        "max_photos": settings.max_photos,
        "max_upload_mb": settings.max_upload_mb,
        "max_clip_mb": settings.max_clip_mb,
    }


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


def test_preflight_response_carries_request_id_and_security_headers(client: TestClient) -> None:
    r = client.options(
        "/healthz",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert len(r.headers["X-Request-ID"]) == 16
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_untrusted_request_id_is_replaced_with_generated_one(client: TestClient) -> None:
    for bad in ("has spaces", "x" * 200, 'quote"me', "bad\r\nX-Injected: yes"):
        rid = client.get("/healthz", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert len(rid) == 16
        assert rid != bad
        int(rid, 16)


def test_writable_probe_is_safe_under_concurrency(settings: Settings) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(_writable, [settings] * 500))


def test_model_api_client_is_ready_on_startup(client: TestClient) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    assert state.model_api.mode == "fixture"
    assert state.ledger.cap_usd == 25.0


def test_api_docs_are_served_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert "/readyz" in client.get("/openapi.json").json()["paths"]


def test_api_docs_off_answers_404_and_the_service_stays_up(settings: Settings) -> None:
    hosted = settings.model_copy(update={"api_docs": False})
    with TestClient(create_app(hosted)) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404, path
        assert c.get("/readyz").status_code == 200
        assert c.get("/healthz").json() == {"status": "ok"}

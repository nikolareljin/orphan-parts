from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.keys import AccessKeys
from app.main import create_app
from app.ops.gate import COOKIE, DEMO_LINE, Allowance, DailyAllowance, Gate, demo_allowed, expensive
from tests.conftest import make_photo

CODE = "a-demo-code-with-length"


def gated_settings(tmp_path: Path, **over: object) -> Settings:
    spec: dict[str, object] = {
        "OPL_FAKE_API": True,
        "data_dir": tmp_path / "data",
        "fixtures_dir": tmp_path / "fixtures",
        "log_format": "text",
        "demo_access_code": CODE,
        "_env_file": None,
    }
    spec.update(over)
    return Settings(**spec)  # type: ignore[arg-type]


@pytest.fixture
def gated(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(gated_settings(tmp_path))) as c:
        yield c


def test_allowance_counts_a_sliding_window_and_says_when_to_come_back() -> None:
    a = Allowance(2, 60)
    assert a.take("x", now=0) == (True, 0)
    assert a.take("x", now=10) == (True, 0)
    ok, retry = a.take("x", now=20)
    assert ok is False and retry == 41  # the first hit leaves the window at 60
    assert a.take("y", now=20) == (True, 0)  # another key, another window
    assert a.take("x", now=61) == (True, 0)
    a.forget("x")
    assert a.take("x", now=62) == (True, 0)


def test_allowance_forgets_addresses_whose_window_has_passed() -> None:
    a = Allowance(2, 60)
    a.SWEEP_EVERY = 10
    for n in range(9):
        a.take(f"visitor-{n}", now=1000.0)
    assert len(a._hits) == 9
    # the tenth take sweeps: every window above has passed, only the new key stays
    a.take("visitor-new", now=1100.0)
    assert list(a._hits) == ["visitor-new"]
    # a key still inside its window is kept by the next sweep
    for n in range(9):
        a.take("visitor-new", now=1100.0 + n)
    assert "visitor-new" in a._hits


def test_daily_allowance_counts_everyone_until_midnight() -> None:
    d = DailyAllowance(2)
    assert d.used == 0
    assert d.take() and d.take() and not d.take()
    assert d.used == 2
    d._day = "2000-01-01"  # a new day: the count starts over
    assert d.used == 0 and d.take()


def test_expensive_names_the_calls_that_spend() -> None:
    assert expensive("POST", "/api/extract")
    assert expensive("POST", "/api/items/12/price")
    assert expensive("POST", "/api/searches/3/candidates")
    assert not expensive("GET", "/api/items/12/price")
    assert not expensive("POST", "/api/items")
    assert not expensive("POST", "/api/assess")


def test_sessions_are_signed_bound_to_the_code_and_end(tmp_path: Path) -> None:
    gate = Gate(gated_settings(tmp_path, demo_session_hours=1))
    token, expires_at = gate.issue(now=1000.0)
    assert expires_at == 4600
    session = gate.verify(token, now=1000.0)
    assert session is not None and session.live is True
    assert gate.verify(token, now=4600.0) is None  # ended
    sid, exp, door, kid, bind, sig = token.split(".")
    assert not Gate.needs_record(token)
    assert Gate.needs_record(f"{sid}.{exp}.{door}.3.{bind}.{sig}")
    assert door == "1" and kid == "0"
    tampered = f"{sid}.{exp}.{door}.{kid}.{bind}.{'0' * 32}"
    assert gate.verify(tampered, now=1000.0) is None
    assert gate.verify(f"{sid}.{int(exp) + 9999}.{door}.{kid}.{bind}.{sig}", now=1000.0) is None
    assert gate.verify(f"{sid}.{exp}.0.{kid}.{bind}.{sig}", now=1000.0) is None  # the door
    assert gate.verify(f"{sid}.{exp}.2.{kid}.{bind}.{sig}", now=1000.0) is None  # no pairing
    assert gate.verify(f"{sid}.{exp}.{door}.7.{bind}.{sig}", now=1000.0) is None  # the key id
    assert gate.verify(f"{sid}.{exp}.{door}.{kid}.{'0' * 16}.{sig}", now=1000.0) is None
    assert gate.verify(f"{sid}.{exp}.{door}.{sig}", now=1000.0) is None  # a malformed token
    assert gate.verify("", now=1000.0) is None and gate.verify("nonsense", now=1000.0) is None
    other = Gate(gated_settings(tmp_path, demo_access_code="another-code-entirely"))
    assert other.verify(token, now=1000.0) is None  # a changed code ends every session
    assert gate.code_matches(CODE) and not gate.code_matches(CODE + "x")
    off = Gate(gated_settings(tmp_path, demo_access_code=None))
    assert off.enabled is False and off.verify(token) is None and not off.code_matches("")


def test_without_a_code_nothing_is_gated(client: TestClient) -> None:
    assert client.get("/api/items").status_code == 200
    body = client.get("/api/access").json()
    assert body == {"gated": False, "granted": True, "live": False, "token": "", "expires_at": 0}
    assert client.post("/api/access", json={"code": "whatever"}).json()["granted"] is True
    demo = client.get("/readyz").json()["demo"]
    assert demo["gated"] is False and demo["paused"] is False and demo["daily_used"] == 0


def test_without_a_session_the_visitor_is_the_demo(gated: TestClient) -> None:
    # the visitor reads what the owner marked public, nothing else; every write is behind the
    # code, with one line that says so
    gated.post("/api/access", json={"code": CODE})
    private = gated.post("/api/items", json={"item_type": "private thing"}).json()["id"]
    shown = gated.post("/api/items", json={"item_type": "public thing"}).json()["id"]
    assert gated.post(f"/api/items/{shown}/public", json={"public": True}).json()["public"] is True
    gated.cookies.clear()
    listed = gated.get("/api/items")
    assert listed.status_code == 200 and [i["id"] for i in listed.json()] == [shown]
    assert gated.get(f"/api/items/{shown}").status_code == 200
    assert gated.get(f"/api/items/{private}").status_code == 404
    assert gated.get(f"/api/items/{private}/photos").status_code == 404
    assert gated.post(f"/api/items/{shown}/public", json={"public": False}).status_code == 403
    assert gated.get(f"/api/items/{shown}/events").json() == {"detail": DEMO_LINE}
    assert gated.post("/api/items", json={"item_type": "x"}).status_code == 403
    captures = gated.get("/api/captures")
    assert captures.status_code == 200 and captures.json() == {"captures": []}
    assert gated.post("/api/captures", data={"request": "{}"}).status_code == 403
    assert gated.get("/api/searches").status_code == 403
    assert gated.post("/api/projects/propose", json={}).status_code == 403
    # the open paths, the profiles and the stateless tries stay reachable
    for path in ("/healthz", "/readyz", "/api/version", "/openapi.json", "/docs", "/api/profiles"):
        assert gated.get(path).status_code == 200, path
    assert gated.get("/api/profiles/power_adapter/rules").status_code == 200
    tried = gated.post("/api/extract", files=[("photos", ("p.jpg", make_photo(), "image/jpeg"))])
    assert tried.status_code not in (401, 403), tried.text
    assert gated.get("/api/access").json()["granted"] is False
    assert gated.get("/readyz").json()["demo"]["gated"] is True
    assert demo_allowed("POST", "/api/assess") and demo_allowed("POST", "/api/measure")
    assert not demo_allowed("POST", "/api/items") and demo_allowed("GET", "/api/items")
    assert not demo_allowed("GET", "/api/searches")
    assert not demo_allowed("GET", "/api/items/1/events")
    assert not demo_allowed("DELETE", "/api/captures/1")


def test_the_right_code_opens_a_session_in_a_cookie_and_as_a_token(gated: TestClient) -> None:
    wrong = gated.post("/api/access", json={"code": "not it"})
    assert wrong.status_code == 401 and "not the access code" in wrong.json()["detail"]
    right = gated.post("/api/access", json={"code": CODE})
    assert right.status_code == 200
    body = right.json()
    assert body["gated"] and body["granted"] and body["token"] and body["expires_at"] > 0
    cookie = right.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Secure" not in cookie  # DEMO_COOKIE_SECURE is off in this test
    assert gated.get("/api/items").status_code == 200  # the client keeps the cookie
    assert gated.get("/api/access").json()["granted"] is True
    gated.cookies.clear()
    assert gated.get("/api/searches").status_code == 403
    bearer = {"Authorization": f"Bearer {body['token']}"}
    assert gated.get("/api/items", headers=bearer).status_code == 200
    nonsense = {"Authorization": "Bearer nonsense"}
    assert gated.get("/api/searches", headers=nonsense).status_code == 403


def test_an_issued_code_opens_the_door_until_it_is_revoked(gated: TestClient) -> None:
    keys = AccessKeys(gated.app.state.inventory.store)
    code, _ = keys.issue("judges", 7)
    opened = gated.post("/api/access", json={"code": code})
    assert opened.status_code == 200 and opened.json()["granted"] is True
    assert gated.get("/api/items").status_code == 200
    # the phone paired from this session carries the same record
    web = {"Origin": "http://host:5173"}
    phone = gated.get("/api/pair", params={"origin": "http://host:5173"}, headers=web).json()[
        "token"
    ]
    bearer = {"Authorization": f"Bearer {phone}"}
    browser = dict(gated.cookies)
    gated.cookies.clear()
    assert gated.get("/api/items", headers=bearer).status_code == 200
    keys.revoke("judges")
    # the sessions it opened end with it, the phone's too, not only new ones
    assert gated.get("/api/searches", headers=bearer).status_code == 403
    gated.cookies.update(browser)
    assert gated.get("/api/searches").status_code == 403
    gated.cookies.clear()
    refused = gated.post("/api/access", json={"code": code})
    assert refused.status_code == 401
    # the master code stands beside the records
    assert gated.post("/api/access", json={"code": CODE}).json()["granted"] is True


def test_with_a_key_the_code_is_the_live_door_and_the_demo_gets_recordings(
    tmp_path: Path,
) -> None:
    settings = gated_settings(
        tmp_path, OPL_FAKE_API=False, OPL_KEY_PROBE=False, model_api_key="sample-key-value"
    )
    with TestClient(create_app(settings)) as c:
        ready = c.get("/readyz").json()
        assert ready["model_api"] == "live for the code, recorded otherwise"
        assert ready["demo"]["live_models"] is True
        assert c.get("/api/access").json() == {
            "gated": True,
            "granted": False,
            "live": False,
            "token": "",
            "expires_at": 0,
        }
        opened = c.post("/api/access", json={"code": CODE}).json()
        assert opened["granted"] is True and opened["live"] is True
        assert c.get("/api/access").json()["live"] is True
        client = c.app.state.model_api
        assert client.twin is not None and client.twin.mode == "fixture"
        assert client.mode == "live"


def test_the_code_may_be_tried_only_so_often(tmp_path: Path) -> None:
    with TestClient(create_app(gated_settings(tmp_path, demo_code_attempts=2))) as c:
        assert c.post("/api/access", json={"code": "a"}).status_code == 401
        assert c.post("/api/access", json={"code": "b"}).status_code == 401
        third = c.post("/api/access", json={"code": CODE})
        assert third.status_code == 429 and "Retry-After" in third.headers


def test_leaving_clears_the_cookie(gated: TestClient) -> None:
    gated.post("/api/access", json={"code": CODE})
    assert gated.get("/api/items").status_code == 200
    gone = gated.delete("/api/access")
    assert gone.status_code == 200 and gone.json()["granted"] is False
    assert (
        "Max-Age=0" in gone.headers["set-cookie"] or "expires" in gone.headers["set-cookie"].lower()
    )
    assert gated.get("/api/searches").status_code == 403  # the demo visitor again


def test_a_record_with_the_same_id_after_a_reset_is_a_stranger(tmp_path: Path) -> None:
    from app.inventory.store import Store

    keys = AccessKeys(Store(tmp_path / "inventory.sqlite3"))
    gate = Gate(gated_settings(tmp_path), keys)
    _, record = keys.issue("judges", 7)
    token, _ = gate.issue(kid=record.id, stamp=record.created_at)
    assert gate.verify(token) is not None
    # the same id, issued at another time (the inventory reset and the code reissued)
    other, _ = gate.issue(kid=record.id, stamp="2026-01-01T00:00:00+00:00")
    assert gate.verify(other) is None
    keys.revoke("judges")
    assert gate.verify(token) is None


def test_the_demo_visitor_never_reads_an_item_through_assess(gated: TestClient) -> None:
    gated.post("/api/access", json={"code": CODE})
    made = gated.post("/api/items", json={"item_type": "vacuum", "profile": "vacuum_attachment"})
    assert made.status_code == 201, made.text
    item_id = made.json()["id"]
    gated.cookies.clear()
    for body in (
        {"need": {"item_id": item_id}, "candidate": {"values": {}}},
        {"need": {"values": {}, "profile": "vacuum_attachment"}, "candidate": {"item_id": item_id}},
        {"need": {"item_id": 999}, "candidate": {"values": {}}},  # nor learns which ids exist
    ):
        refused = gated.post("/api/assess", json=body)
        assert refused.status_code == 403 and refused.json()["detail"] == DEMO_LINE, body
    # values written in are the demo's try
    tried = gated.post(
        "/api/assess",
        json={"need": {"values": {}, "profile": "vacuum_attachment"}, "candidate": {"values": {}}},
    )
    assert tried.status_code == 200, tried.text


def test_the_demo_visitors_tries_are_counted_per_address(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path, demo_visitor_calls_per_hour=2)
    with TestClient(create_app(settings)) as c:
        photo = [("photos", ("p.jpg", make_photo(), "image/jpeg"))]
        c.post("/api/extract", files=photo)
        c.post("/api/extract", files=photo)
        third = c.post("/api/extract", files=photo)
        assert third.status_code == 429 and "tries" in third.json()["detail"]
        # every try counts, the cheap ones too
        need = {"need": {"values": {}, "profile": "vacuum_attachment"}, "candidate": {"values": {}}}
        assert c.post("/api/assess", json=need).status_code == 429
        assert c.get("/readyz").json()["demo"]["daily_used"] == 0  # nothing spent
        assert c.get("/api/templates").status_code == 200  # looking stays open


def test_what_spends_is_counted_per_visitor_and_per_day(tmp_path: Path) -> None:
    # an empty fixtures directory: the call is counted before it is made, whatever it answers
    settings = gated_settings(tmp_path, demo_visitor_calls_per_hour=2, demo_daily_calls=3)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        photo = [("photos", ("p.jpg", make_photo(), "image/jpeg"))]
        first = c.post("/api/extract", files=photo)
        assert first.status_code != 401 and first.status_code != 429, first.text
        c.post("/api/extract", files=photo)
        third = c.post("/api/extract", files=photo)
        assert third.status_code == 429
        assert "hourly allowance" in third.json()["detail"] and "Retry-After" in third.headers
        # reading costs nothing and stays open
        assert c.get("/api/items").status_code == 200
        assert c.get("/readyz").json()["demo"]["daily_used"] == 2
        # the demo visitor's tries are recordings: not counted, not refused by the allowance
        kept = dict(c.cookies)
        c.cookies.clear()
        tried = c.post("/api/extract", files=photo)
        assert tried.status_code != 429, tried.text
        assert c.get("/readyz").json()["demo"]["daily_used"] == 2
        c.cookies.update(kept)
        # another visitor shares the day
        c.cookies.clear()
        c.post("/api/access", json={"code": CODE})
        c.post("/api/extract", files=photo)
        fourth = c.post("/api/extract", files=photo)
        assert fourth.status_code == 429 and "daily allowance" in fourth.json()["detail"]


def test_the_operator_switch_refuses_only_what_spends(tmp_path: Path) -> None:
    with TestClient(create_app(gated_settings(tmp_path, demo_paused=True))) as c:
        c.post("/api/access", json={"code": CODE})
        item = c.post("/api/items", json={"item_type": "kettle"})
        assert item.status_code == 201
        paused = c.post(f"/api/items/{item.json()['id']}/drafts", json={"mode": "sell"})
        assert paused.status_code == 503 and "paused by the operator" in paused.json()["detail"]
        assert c.get("/readyz").json()["demo"]["paused"] is True


def test_every_request_has_a_per_address_limit_even_without_a_code(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path, demo_access_code=None, demo_requests_per_minute=3)
    with TestClient(create_app(settings)) as c:
        for _ in range(3):
            assert c.get("/api/items").status_code == 200
        limited = c.get("/api/items")
        assert limited.status_code == 429 and "Retry-After" in limited.headers
        assert c.get("/healthz").status_code == 200  # the open paths are never limited
        assert "X-Request-ID" in limited.headers  # a refusal is answered like any other


def test_the_forwarded_address_counts_only_when_the_proxy_is_trusted(tmp_path: Path) -> None:
    gate = Gate(gated_settings(tmp_path, demo_trust_proxy=False))

    class Client:
        host = "10.0.0.9"

    class Req:
        # the first entry is whatever the caller sent; the proxy appended the last one
        headers = {"x-forwarded-for": "198.51.100.1, 203.0.113.7"}
        client = Client()

    assert gate.client_ip(Req()) == "10.0.0.9"  # type: ignore[arg-type]
    trusting = Gate(gated_settings(tmp_path, demo_trust_proxy=True))
    assert trusting.client_ip(Req()) == "203.0.113.7"  # type: ignore[arg-type]

    class One(Req):
        headers = {"x-forwarded-for": "203.0.113.8"}

    assert trusting.client_ip(One()) == "203.0.113.8"  # type: ignore[arg-type]

    class Odd(Req):
        headers = {"x-forwarded-for": "not an address"}

    assert trusting.client_ip(Odd()) == "10.0.0.9"  # type: ignore[arg-type]


def test_demo_settings_are_checked(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="DEMO_ACCESS_CODE"):
        gated_settings(tmp_path, demo_access_code="short")
    with pytest.raises(ValueError, match="DEMO_DAILY_CALLS"):
        gated_settings(tmp_path, demo_daily_calls=0)


def test_a_forged_token_is_refused_before_any_record_is_read(tmp_path: Path) -> None:
    from app.inventory.store import Store

    keys = AccessKeys(Store(tmp_path / "inventory.sqlite3"))
    gate = Gate(gated_settings(tmp_path), keys)
    _, record = keys.issue("judges", 7)
    token, _ = gate.issue(kid=record.id, stamp=record.created_at)
    reads: list[int] = []
    real = keys.stamp

    def counted(kid: int) -> str | None:
        reads.append(kid)
        return real(kid)

    keys.stamp = counted  # type: ignore[method-assign]
    sid, exp, door, kid, bind, sig = token.split(".")
    for forged in (
        f"{sid}.{exp}.{door}.{kid}.{bind}.{'a' * 32}",
        f"{sid}.{exp}.{door}.99.{bind}.{sig}",
        f"forgedsid1.{exp}.1.{kid}.{'b' * 16}.{'c' * 32}",
    ):
        assert gate.verify(forged) is None
    assert reads == []
    # the real one reads its record once, so revoking the record still ends it
    assert gate.verify(token) is not None and reads == [record.id]


def test_a_session_of_the_shape_before_the_binding_still_opens_the_door(tmp_path: Path) -> None:
    import hashlib
    import hmac
    import time

    from app.inventory.store import Store

    keys = AccessKeys(Store(tmp_path / "inventory.sqlite3"))
    gate = Gate(gated_settings(tmp_path), keys)
    _, record = keys.issue("judges", 7)
    key = hashlib.sha256(b"opl-session:" + CODE.encode()).digest()

    def old(exp: int, kid: int, stamp: str) -> str:
        text = f"oldsession1.{exp}.1.{kid}.{stamp}".encode()
        return f"oldsession1.{exp}.1.{kid}." + hmac.new(key, text, hashlib.sha256).hexdigest()[:32]

    soon = int(time.time()) + 600
    found = gate.verify(old(soon, 0, ""))
    assert found is not None and found.live and not found.pairing
    assert gate.verify(old(soon, record.id, record.created_at)) is not None
    # one ending past what any session issued before this process could reach is not ours
    assert gate.verify(old(soon + gate.session_seconds, 0, "")) is None
    keys.revoke("judges")
    assert gate.verify(old(soon, record.id, record.created_at)) is None

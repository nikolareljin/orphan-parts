import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inventory.store import Store
from app.keys import AccessKeys
from app.main import create_app
from app.ops.gate import Gate
from app.pairing import BadOriginError, Pairing, pairing, svg, terminal
from app.pairing.__main__ import main

CODE = "a-demo-code-of-twelve"
# the page the tests stand for: opened at this origin, so the pairing may carry it
WEB = "http://host:5173"


def gated(tmp_path: Path, **over: object) -> Settings:
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


def served(settings: Settings) -> TestClient:
    """A client whose requests name the web app's origin as their host, as the browser's do."""
    return TestClient(create_app(settings), base_url=WEB)


def pair_token(c: TestClient, session: str = "") -> str:
    """A pairing from the signed-in page: by the cookie, or by ``session`` as a bearer."""
    headers = bearer(session) if session else {}
    found = c.get("/api/pair", params={"origin": WEB}, headers=headers)
    assert found.status_code == 200, found.text
    return str(found.json()["token"])


def save(c: TestClient, session: str) -> int:
    return c.post("/api/items", json={"item_type": "x"}, headers=bearer(session)).status_code


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def claim(c: TestClient, token: str) -> tuple[int, dict[str, object]]:
    found = c.post("/api/pair/code", headers=bearer(token))
    return found.status_code, found.json()


def test_the_pairing_carries_a_session_only_when_gated(settings: Settings, tmp_path: Path) -> None:
    open_gate = Gate(settings)
    found = pairing("http://192.168.1.20:5173", open_gate)
    assert found.url == "http://192.168.1.20:5173" and not found.gated and found.token == ""
    assert json.loads(found.payload()) == {
        "url": "http://192.168.1.20:5173",
        "gated": False,
        "token": "",
    }
    gate = Gate(gated(tmp_path))
    found = pairing("https://demo.example", gate)
    assert found.gated and found.token and found.expires_at > 0
    assert gate.verify(found.token) is not None
    # the demo visitor's pairing: the address, that the demo is gated, and no session
    alone = pairing("https://demo.example", gate, visitor=True)
    assert alone.gated and alone.token == "" and alone.expires_at == 0
    assert json.loads(alone.payload()) == {
        "url": "https://demo.example",
        "gated": True,
        "token": "",
    }
    # an IPv6 host in brackets is an origin too
    assert pairing("http://[fd00::2]:5173", open_gate).url == "http://[fd00::2]:5173"
    for bad in (
        "demo.example",
        "http://demo.example/api",
        "http://demo.example:5173/",
        "ftp://x",
        "",
    ):
        with pytest.raises(BadOriginError):
            pairing(bad, gate)


def test_the_code_is_an_svg_and_a_terminal_block() -> None:
    found = Pairing(url="http://host:5173", gated=False)
    image = svg(found)
    assert image.startswith(b"<?xml") and b"<svg" in image
    text = terminal(found)
    assert text.count("\n") > 10


def test_pair_routes_need_a_session_when_gated(settings: Settings, tmp_path: Path) -> None:
    with served(settings) as c:
        found = c.get("/api/pair", params={"origin": "http://host:5173"})
        assert found.status_code == 200 and found.json()["gated"] is False
        image = c.get("/api/pair.svg", params={"origin": "http://host:5173"})
        assert image.status_code == 200 and image.headers["content-type"].startswith(
            "image/svg+xml"
        )
        assert image.headers["cache-control"] == "no-store"
        assert c.get("/api/pair", params={"origin": "host"}).status_code == 422
        assert c.get("/api/pair").status_code == 422
    with served(gated(tmp_path)) as c:
        # the demo visitor pairs a phone as the demo visitor: the address, never a session
        alone = c.get("/api/pair", params={"origin": "http://host:5173"})
        assert alone.status_code == 200
        assert alone.json() == {
            "name": "Orphan Parts Lens",
            "url": "http://host:5173",
            "gated": True,
            "token": "",
            "expires_at": 0,
        }
        assert c.get("/api/pair.svg", params={"origin": "http://host:5173"}).status_code == 200
        # and the rest of the gate stands as it was
        assert c.post("/api/items", json={"item_type": "x"}).status_code == 403
        assert c.post("/api/pair/code").status_code == 401
        c.post("/api/access", json={"code": CODE})
        found = c.get("/api/pair", params={"origin": "http://host:5173"}).json()
        assert found["gated"] is True and found["token"]
        # the pairing opens the gate as a bearer header, for its few minutes
        c.cookies.clear()
        assert (
            c.get("/api/items", headers={"Authorization": f"Bearer {found['token']}"}).status_code
            == 200
        )
        assert found["token"].split(".")[2] == "2"
        assert 14 * 60 < found["expires_at"] - datetime.now(UTC).timestamp() <= 15 * 60


def test_the_command_line_prints_the_code_or_the_payload(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import app.pairing.__main__ as cli

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert main([]) == 2
    assert main(["--what"]) == 2
    assert main(["--origin", "nowhere"]) == 1
    assert main(["--origin", "http://host:5173", "--json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["url"] == "http://host:5173"
    assert main(["--origin", "http://host:5173"]) == 0
    out = capsys.readouterr().out
    assert "http://host:5173  (no code needed)" in out


def test_a_scanned_phone_claims_a_code_of_its_own_once(tmp_path: Path) -> None:
    settings = gated(tmp_path, pair_code_days=30)
    with served(settings) as c:
        # no session, or not one of ours: 401
        assert c.post("/api/pair/code").status_code == 401
        assert c.post("/api/pair/code", headers=bearer("not.a.token")).status_code == 401
        c.post("/api/access", json={"code": CODE})
        token = pair_token(c)
        c.cookies.clear()
        status, own = claim(c, token)
        assert status == 200 and own["gated"] is True
        assert str(own["code"]).startswith("opl_")
        sid = token.split(".")[0]
        assert own["label"] == f"phone {sid[:8]}"
        # the master code's pairing gets the full PAIR_CODE_DAYS
        until = datetime.fromisoformat(str(own["expires_at"]))
        assert timedelta(days=29, hours=23) < until - datetime.now(UTC) <= timedelta(days=30)
        # one claim per pairing
        status, again = claim(c, token)
        assert status == 403 and "already" in str(again["detail"])
        # the code opens a session like a typed one, with no scan
        opened = c.post("/api/access", json={"code": own["code"]})
        assert opened.status_code == 200 and opened.json()["granted"] is True
        session = opened.json()["token"]
        c.cookies.clear()
        saved = c.post("/api/items", json={"item_type": "x"}, headers=bearer(session))
        assert saved.status_code == 201
        # it is a record like any other: listed, and revoked by its label with its sessions
        keys = c.app.state.gate.keys  # type: ignore[attr-defined]
        assert [k.label for k in keys.all()] == [own["label"]]
        keys.revoke(str(own["label"]))
        refused = c.post("/api/items", json={"item_type": "x"}, headers=bearer(session))
        assert refused.status_code == 403
        assert c.post("/api/access", json={"code": own["code"]}).status_code == 401
        # the pairing still stands, but its one claim is spent, revoked or not
        assert claim(c, token)[0] == 403


def test_a_browser_session_cannot_claim_a_phone_code(tmp_path: Path) -> None:
    with served(gated(tmp_path)) as c:
        session = c.post("/api/access", json={"code": CODE}).json()["token"]
        # by the cookie the browser keeps
        refused = c.post("/api/pair/code")
        assert refused.status_code == 403 and "browser" in refused.json()["detail"]
        c.cookies.clear()
        # or by the same session as a bearer
        assert claim(c, session)[0] == 403
        assert c.app.state.gate.keys.all() == []  # type: ignore[attr-defined]


def test_a_pairing_ends_within_minutes(tmp_path: Path) -> None:
    settings = gated(tmp_path, pair_token_minutes=5)
    with served(settings) as c:
        c.post("/api/access", json={"code": CODE})
        token = pair_token(c)
        c.cookies.clear()
        gate = c.app.state.gate  # type: ignore[attr-defined]
        now = datetime.now(UTC).timestamp()
        exp = int(token.split(".")[1])
        assert 4 * 60 < exp - now <= 5 * 60
        assert gate.verify(token, now=exp - 1) is not None
        assert gate.verify(token, now=exp) is None
        # a pairing does not hand out another pairing: the address alone
        again = c.get("/api/pair", params={"origin": WEB}, headers=bearer(token)).json()
        assert again["token"] == ""


def test_the_demo_door_gets_no_pairing_and_cannot_claim(tmp_path: Path) -> None:
    with served(gated(tmp_path)) as c:
        gate = c.app.state.gate  # type: ignore[attr-defined]
        demo, _ = gate.issue(live=False)
        found = c.get("/api/pair", params={"origin": WEB}, headers=bearer(demo)).json()
        assert found["gated"] is True and found["token"] == ""
        assert claim(c, demo)[0] == 401


def test_revoking_the_code_that_paired_a_phone_ends_the_phones_code(tmp_path: Path) -> None:
    settings = gated(tmp_path, pair_code_days=30)
    with served(settings) as c:
        keys = c.app.state.gate.keys  # type: ignore[attr-defined]
        guest, _ = keys.issue("guest", 7)
        session = c.post("/api/access", json={"code": guest}).json()["token"]
        c.cookies.clear()
        status, own = claim(c, pair_token(c, session))
        assert status == 200
        phone = c.post("/api/access", json={"code": own["code"]}).json()["token"]
        c.cookies.clear()
        assert save(c, phone) == 201
        listed = {k.label: k for k in keys.all()}
        assert listed[str(own["label"])].parent_id == listed["guest"].id
        keys.revoke("guest")
        # the phone's session and its code end with the guest's code
        assert save(c, phone) == 403
        assert c.post("/api/access", json={"code": own["code"]}).status_code == 401
        assert {k.label: k.state() for k in keys.all()}[str(own["label"])] == "ended"


def test_a_phone_code_does_not_pair_another_phone(tmp_path: Path) -> None:
    with served(gated(tmp_path)) as c:
        keys = c.app.state.gate.keys  # type: ignore[attr-defined]
        guest, _ = keys.issue("guest", 7)
        session = c.post("/api/access", json={"code": guest}).json()["token"]
        c.cookies.clear()
        own = claim(c, pair_token(c, session))[1]
        phone = c.post("/api/access", json={"code": own["code"]}).json()["token"]
        c.cookies.clear()
        status, refused = claim(c, pair_token(c, phone))
        assert status == 403 and "another phone" in str(refused["detail"])


def test_a_new_master_code_ends_the_phone_codes_claimed_under_the_old(tmp_path: Path) -> None:
    with served(gated(tmp_path)) as c:
        c.post("/api/access", json={"code": CODE})
        token = pair_token(c)
        c.cookies.clear()
        own = claim(c, token)[1]
        assert c.post("/api/access", json={"code": own["code"]}).status_code == 200
    rotated = gated(tmp_path, demo_access_code="another-master-code")
    with served(rotated) as c:
        assert c.post("/api/access", json={"code": own["code"]}).status_code == 401
        listed = c.app.state.gate.keys.all()  # type: ignore[attr-defined]
        assert [k.state() for k in listed] == ["ended"] and listed[0].master
    # the same code again: the phone's code stands again, nothing was written
    with served(gated(tmp_path)) as c:
        assert c.post("/api/access", json={"code": own["code"]}).status_code == 200


def test_the_claim_counts_against_the_code_attempts(tmp_path: Path) -> None:
    with served(gated(tmp_path, demo_code_attempts=2)) as c:
        assert c.post("/api/pair/code").status_code == 401
        assert c.post("/api/pair/code").status_code == 401
        spent = c.post("/api/pair/code")
        assert spent.status_code == 429 and "Retry-After" in spent.headers
        # the access code shares the allowance
        assert c.post("/api/access", json={"code": CODE}).status_code == 429


def test_claims_that_work_keep_the_address_tries(tmp_path: Path) -> None:
    with served(gated(tmp_path, demo_code_attempts=5)) as c:
        c.post("/api/access", json={"code": CODE})
        tokens = [pair_token(c) for _ in range(8)]
        c.cookies.clear()
        assert [claim(c, token)[0] for token in tokens] == [200] * 8
        assert c.post("/api/access", json={"code": CODE}).status_code == 200


def test_only_an_origin_this_server_is_reached_at_goes_into_a_pairing(tmp_path: Path) -> None:
    lan = "http://192.168.1.20:5173"
    evil = {"origin": "https://evil.example"}
    with TestClient(create_app(gated(tmp_path))) as c:
        # anonymous, and signed in
        assert c.get("/api/pair", params=evil).status_code == 422
        assert c.get("/api/pair.svg", params=evil).status_code == 422
        c.post("/api/access", json={"code": CODE})
        refused = c.get("/api/pair", params=evil)
        assert refused.status_code == 422 and "not an origin" in refused.json()["detail"]
        # another site's page naming itself: the browser marks its requests cross-site
        for page in ({"Origin": "https://evil.example"}, {"Referer": "https://evil.example/"}):
            asked_from = {**page, "Sec-Fetch-Site": "cross-site"}
            assert c.get("/api/pair", params=evil, headers=asked_from).status_code == 422
            assert c.get("/api/pair.svg", params=evil, headers=asked_from).status_code == 422
        # nor as the API's origin beside a good web origin
        asked = {"origin": lan, "api": "https://evil.example"}
        same = {"Origin": lan, "Sec-Fetch-Site": "same-origin"}
        assert c.get("/api/pair", params=asked, headers=same).status_code == 422
        # the page on the network through the dev server, which rewrites the Host and forwards
        # the one the browser asked for; a plain http:// page on the LAN gets no Sec-Fetch-Site
        vite = {
            "Host": "backend:8000",
            "X-Forwarded-Host": "192.168.1.20:5173",
            "X-Forwarded-Proto": "http",
            "Referer": lan + "/",
        }
        assert c.get("/api/pair", params={"origin": lan}, headers=vite).json()["token"]
        image = c.get("/api/pair.svg", params={"origin": lan}, headers=vite)
        assert image.status_code == 200 and image.headers["content-type"] == "image/svg+xml"
        # the forwarded scheme is the one the page was served over
        https_lan = {"origin": "https://192.168.1.20:5173"}
        assert c.get("/api/pair.svg", params=https_lan, headers=vite).status_code == 422
        # through nginx, which keeps the host and port the browser asked for
        nginx = {"Host": "192.168.1.20:8080", "X-Forwarded-Host": "192.168.1.20:8080"}
        found = c.get("/api/pair.svg", params={"origin": "http://192.168.1.20:8080"}, headers=nginx)
        assert found.status_code == 200
        assert (
            c.get(
                "/api/pair.svg",
                params={"origin": "http://192.168.1.20:8080"},
                headers={"Host": "192.168.1.20:8080"},
            ).status_code
            == 200
        )
        # another site's page loading the image through that same proxy names nothing but it
        cross = {**vite, "Referer": "https://evil.example/", "Sec-Fetch-Site": "cross-site"}
        assert c.get("/api/pair.svg", params=evil, headers=cross).status_code == 422
        # the page's Origin or Referer alone, without the browser's same-origin mark, names nothing
        unmarked = c.get("/api/pair", params={"origin": lan}, headers={"Origin": lan})
        assert unmarked.status_code == 422
        lan_image = {"Referer": lan + "/"}
        assert c.get("/api/pair.svg", params={"origin": lan}, headers=lan_image).status_code == 422
    # the hosted page on another origin, named in CORS_ORIGINS, with the API's own origin
    pages = "https://orphan-parts.pages.dev"
    settings = gated(tmp_path / "hosted", cors_origins=pages)
    with TestClient(create_app(settings), base_url="https://api.example") as c:
        found = c.get("/api/pair", params={"origin": pages, "api": "https://api.example"})
        assert found.status_code == 200 and found.json()["url"] == "https://api.example"


def test_pairing_settings_have_bounds(tmp_path: Path) -> None:
    for over in (
        {"pair_code_days": 0},
        {"pair_code_days": 3651},
        {"pair_token_minutes": 0},
        {"pair_token_minutes": 61},
    ):
        with pytest.raises(ValueError, match="must be between"):
            gated(tmp_path, **over)
    assert gated(tmp_path, pair_code_days=3650, pair_token_minutes=60).pair_code_days == 3650


def test_a_phone_code_never_outlives_the_code_that_paired_it(tmp_path: Path) -> None:
    settings = gated(tmp_path, pair_code_days=30)
    keys = AccessKeys(Store(settings.inventory_db_path))
    with served(settings) as c:
        judges, record = keys.issue("judges", 3)
        session = c.post("/api/access", json={"code": judges}).json()["token"]
        c.cookies.clear()
        status, own = claim(c, pair_token(c, session))
        assert status == 200 and own["expires_at"] == record.expires_at
        # a parent with no expiry gives the full count
        forever, _ = keys.issue("family")
        session = c.post("/api/access", json={"code": forever}).json()["token"]
        c.cookies.clear()
        status, own = claim(c, pair_token(c, session))
        assert status == 200
        until = datetime.fromisoformat(str(own["expires_at"]))
        assert until - datetime.now(UTC) > timedelta(days=29)
        # a parent that has expired gives nothing, though its pairing is still signed
        session = c.post("/api/access", json={"code": forever}).json()["token"]
        c.cookies.clear()
        token = pair_token(c, session)
        kid = token.split(".")[3]
        with Store(settings.inventory_db_path).connect() as conn:
            conn.execute(
                "UPDATE access_keys SET expires_at = ? WHERE id = ?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), int(kid)),
            )
        status, refused = claim(c, token)
        assert status == 403 and "has ended" in str(refused["detail"])
        # a revoked parent ends the pairing itself
        keys.revoke("judges")
        other, _ = keys.issue("visitor", 2)
        session = c.post("/api/access", json={"code": other}).json()["token"]
        c.cookies.clear()
        token = pair_token(c, session)
        keys.revoke("visitor")
        assert claim(c, token)[0] == 401


def test_without_a_gate_there_is_no_code_to_claim(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        found = c.post("/api/pair/code")
        assert found.status_code == 200
        assert found.json() == {"gated": False, "code": "", "label": "", "expires_at": None}

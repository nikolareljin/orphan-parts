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


def gated(tmp_path: Path, **over: object) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        demo_access_code=CODE,
        _env_file=None,
        **over,
    )


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
    with TestClient(create_app(settings)) as c:
        found = c.get("/api/pair", params={"origin": "http://host:5173"})
        assert found.status_code == 200 and found.json()["gated"] is False
        image = c.get("/api/pair.svg", params={"origin": "http://host:5173"})
        assert image.status_code == 200 and image.headers["content-type"].startswith(
            "image/svg+xml"
        )
        assert image.headers["cache-control"] == "no-store"
        assert c.get("/api/pair", params={"origin": "host"}).status_code == 422
        assert c.get("/api/pair").status_code == 422
    with TestClient(create_app(gated(tmp_path))) as c:
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
        # the phone's session works as a bearer header
        c.cookies.clear()
        assert (
            c.get("/api/items", headers={"Authorization": f"Bearer {found['token']}"}).status_code
            == 200
        )


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
    with TestClient(create_app(settings)) as c:
        # no session, or not one of ours: 401
        assert c.post("/api/pair/code").status_code == 401
        assert c.post("/api/pair/code", headers=bearer("not.a.token")).status_code == 401
        c.post("/api/access", json={"code": CODE})
        token = c.get("/api/pair", params={"origin": "http://host:5173"}).json()["token"]
        c.cookies.clear()
        status, own = claim(c, token)
        assert status == 200 and own["gated"] is True
        assert str(own["code"]).startswith("opl_")
        sid = token.split(".")[0]
        assert own["label"] == f"phone {sid[:8]}"
        # the master code's session gets the full PAIR_CODE_DAYS
        until = datetime.fromisoformat(str(own["expires_at"]))
        assert timedelta(days=29, hours=23) < until - datetime.now(UTC) <= timedelta(days=30)
        # one claim per pairing session
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
        keys = AccessKeys(Store(settings.inventory_db_path))
        assert [k.label for k in keys.all()] == [own["label"]]
        keys.revoke(str(own["label"]))
        refused = c.post("/api/items", json={"item_type": "x"}, headers=bearer(session))
        assert refused.status_code == 403
        assert c.post("/api/access", json={"code": own["code"]}).status_code == 401
        # the pairing session still stands, but its one claim is spent, revoked or not
        assert claim(c, token)[0] == 403


def test_a_phone_code_never_outlives_the_code_that_paired_it(tmp_path: Path) -> None:
    settings = gated(tmp_path, pair_code_days=30)
    keys = AccessKeys(Store(settings.inventory_db_path))
    with TestClient(create_app(settings)) as c:
        judges, record = keys.issue("judges", 3)
        session = c.post("/api/access", json={"code": judges}).json()["token"]
        c.cookies.clear()
        token = c.get(
            "/api/pair", params={"origin": "http://host:5173"}, headers=bearer(session)
        ).json()["token"]
        status, own = claim(c, token)
        assert status == 200 and own["expires_at"] == record.expires_at
        # a parent with no expiry gives the full count
        forever, _ = keys.issue("family")
        session = c.post("/api/access", json={"code": forever}).json()["token"]
        c.cookies.clear()
        token = c.get(
            "/api/pair", params={"origin": "http://host:5173"}, headers=bearer(session)
        ).json()["token"]
        status, own = claim(c, token)
        assert status == 200
        until = datetime.fromisoformat(str(own["expires_at"]))
        assert until - datetime.now(UTC) > timedelta(days=29)
        # a parent that has expired gives nothing, though its session is still signed
        session = c.post("/api/access", json={"code": forever}).json()["token"]
        c.cookies.clear()
        token = c.get(
            "/api/pair", params={"origin": "http://host:5173"}, headers=bearer(session)
        ).json()["token"]
        kid = token.split(".")[3]
        with Store(settings.inventory_db_path).connect() as conn:
            conn.execute(
                "UPDATE access_keys SET expires_at = ? WHERE id = ?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), int(kid)),
            )
        status, refused = claim(c, token)
        assert status == 403 and "has ended" in str(refused["detail"])
        # a revoked parent ends the pairing session itself
        keys.revoke("judges")
        other, _ = keys.issue("visitor", 2)
        session = c.post("/api/access", json={"code": other}).json()["token"]
        c.cookies.clear()
        token = c.get(
            "/api/pair", params={"origin": "http://host:5173"}, headers=bearer(session)
        ).json()["token"]
        keys.revoke("visitor")
        assert claim(c, token)[0] == 401


def test_without_a_gate_there_is_no_code_to_claim(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        found = c.post("/api/pair/code")
        assert found.status_code == 200
        assert found.json() == {"gated": False, "code": "", "label": "", "expires_at": None}

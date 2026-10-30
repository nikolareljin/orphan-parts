import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ops.gate import Gate
from app.pairing import BadOriginError, Pairing, pairing, svg, terminal
from app.pairing.__main__ import main

CODE = "a-demo-code-of-twelve"


def gated(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        demo_access_code=CODE,
        _env_file=None,
    )


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
        assert c.get("/api/pair", params={"origin": "http://host:5173"}).status_code == 401
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

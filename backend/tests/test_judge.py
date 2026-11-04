"""Judges' codes: read-only on the demo set (the owner's records), a sandbox of their own,
private fields left out, live calls capped per code before they are made, the recordings only
when the code says so, and the codes kept through a demo reset."""

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo.service import reset
from app.keys import AccessKeyError, AccessKeys
from app.keys.__main__ import main
from app.keys.service import BUDGET_LINE, DAILY_CALLS_LINE
from app.keys.store import keys_store, open_keys
from app.main import create_app
from app.model_api import CodeLimitError, CostLedger, FixtureMissingError, ModelApiClient
from app.ops.door import code_meter, judge_code, live_request, recorded_request
from app.ops.gate import JUDGE_CREATE, JUDGE_LINE, OPEN_PATHS, CodeMeter
from tests.test_gate import CODE, gated_settings

# --- the codes ------------------------------------------------------------------


def test_scopes_and_limits_are_checked_on_issue(tmp_path: Path) -> None:
    keys = AccessKeys(keys_store(tmp_path / "k.sqlite3"))
    _, owner = keys.issue("family")
    assert owner.scope == "owner" and owner.calls_per_day is None and owner.max_usd is None
    _, judge = keys.issue("jury", 10, scope="judge")
    assert judge.judge and judge.calls_per_day == 20 and judge.max_usd == 5.0
    _, tape = keys.issue("tape", scope="judge", recorded=True, calls_per_day=3, max_usd=0.5)
    assert tape.recorded and tape.calls_per_day == 3 and tape.max_usd == 0.5
    with pytest.raises(AccessKeyError, match="--scope judge"):
        keys.issue("owner-capped", calls_per_day=5)
    with pytest.raises(AccessKeyError, match="--scope judge"):
        keys.issue("owner-recorded", recorded=True)
    with pytest.raises(AccessKeyError, match="scope"):
        keys.issue("odd", scope="admin")  # type: ignore[arg-type]
    with pytest.raises(AccessKeyError, match="0 or more"):
        keys.issue("negative", scope="judge", max_usd=-1)
    # read back as written
    assert [(k.label, k.scope) for k in keys.all()] == [
        ("family", "owner"),
        ("jury", "judge"),
        ("tape", "judge"),
    ]
    # a judge's code pairs no phone
    with pytest.raises(AccessKeyError, match="judge"):
        keys.issue_child("phone", 5, parent=judge.id, stamp=judge.created_at)


def test_the_command_issues_a_judge_code_and_lists_its_use(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    keys = AccessKeys(keys_store(tmp_path / "k.sqlite3"))
    args = ["issue", "--label", "jury", "--days", "10", "--scope", "judge"]
    assert main([*args, "--calls-per-day", "20", "--max-usd", "5"], keys) == 0
    out, err = capsys.readouterr()
    assert out.startswith("jury: opl_")
    assert "judge scope, 20 calls a day, $5.00 in all" in err
    assert main(["issue", "--label", "tape", "--scope", "judge", "--recorded"], keys) == 0
    assert "recorded answers only" in capsys.readouterr()[1]
    assert main(["issue", "--label", "x", "--max-usd", "1"], keys) == 2
    assert "--scope judge" in capsys.readouterr()[1]
    jury = keys.all()[0]
    keys.charge(jury.id, 0.41)
    keys.charge(jury.id, 0.1)
    assert main(["list"], keys) == 0
    out = capsys.readouterr()[0]
    line = next(r for r in out.splitlines() if "\tjury\t" in r)
    assert "\tjudge\tcurrent\tcalls 2/20 today\t$0.51/$5.00\t" in line
    assert "\ttape\tjudge\tcurrent\tcalls 0/20 today\t$0.00/$5.00 recorded" in out


def test_usage_is_per_code_per_day_and_refused_at_the_limit(tmp_path: Path) -> None:
    keys = AccessKeys(keys_store(tmp_path / "k.sqlite3"))
    _, jury = keys.issue("jury", scope="judge", calls_per_day=2, max_usd=1.0)
    _, other = keys.issue("other", scope="judge")
    keys.check(jury.id)
    keys.charge(jury.id, 0.2)
    keys.charge(jury.id, 0.2)
    assert keys.usage(jury.id).calls_today == 2 and keys.usage(other.id).calls_today == 0
    with pytest.raises(CodeLimitError) as calls:
        keys.check(jury.id)
    assert calls.value.status == 429 and str(calls.value) == DAILY_CALLS_LINE
    # yesterday's calls do not count today; the dollars always do
    with keys.store.connect() as conn:
        conn.execute("UPDATE key_usage SET day = '2000-01-01', usd = 1.0")
    assert keys.usage(jury.id).calls_today == 0
    with pytest.raises(CodeLimitError) as budget:
        keys.check(jury.id)
    assert budget.value.status == 403 and str(budget.value) == BUDGET_LINE
    keys.revoke("other")
    with pytest.raises(CodeLimitError, match="ended"):
        keys.check(other.id)


# --- the client: limits before each call, the charge beside the ledger, the recordings --


def _answer(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            "usage": {"input_tokens": 1000, "output_tokens": 1000},
        },
    )


@pytest.mark.anyio
async def test_the_client_checks_the_code_before_each_paid_call_and_charges_it(
    live_settings: Settings, tmp_path: Path
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _answer(request)

    keys = AccessKeys(keys_store(tmp_path / "k.sqlite3"))
    _, jury = keys.issue("jury", scope="judge", calls_per_day=2, max_usd=100.0)
    ledger = CostLedger(25.0)
    client = ModelApiClient(live_settings, ledger, transport=httpx.MockTransport(handler))
    token = code_meter.set(CodeMeter(keys, jury.id))
    try:
        for _ in range(2):
            await client.respond(model=live_settings.model_spark, input="hi", op="extract")
        with pytest.raises(CodeLimitError) as refused:
            await client.respond(model=live_settings.model_spark, input="hi", op="extract")
    finally:
        code_meter.reset(token)
    assert refused.value.status == 429
    # the third was never sent; the two that were are on the ledger and on the code alike
    assert len(calls) == 2 and len(ledger.entries()) == 2
    used = keys.usage(jury.id)
    assert used.calls_today == 2 and used.usd == pytest.approx(ledger.total_usd)
    assert used.usd > 0
    # the budget is checked the same way
    _, poor = keys.issue("poor", scope="judge", max_usd=0.0)
    token = code_meter.set(CodeMeter(keys, poor.id))
    try:
        with pytest.raises(CodeLimitError) as spent:
            await client.respond(model=live_settings.model_spark, input="hi", op="extract")
    finally:
        code_meter.reset(token)
    assert spent.value.status == 403 and len(calls) == 2
    # the master code (no meter) is unaffected
    await client.respond(model=live_settings.model_spark, input="hi", op="extract")
    assert len(calls) == 3
    await client.aclose()


@pytest.mark.anyio
async def test_a_recorded_code_never_reaches_the_key(
    live_settings: Settings, tmp_path: Path
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _answer(request)

    client = ModelApiClient(live_settings, CostLedger(25.0), transport=httpx.MockTransport(handler))
    client.twin = ModelApiClient(
        live_settings.model_copy(update={"fake_api": True, "fixtures_dir": tmp_path / "none"}),
        CostLedger(25.0),
    )
    door, tape = live_request.set(True), recorded_request.set(True)
    try:
        with pytest.raises(FixtureMissingError):
            await client.respond(model=live_settings.model_spark, input="hi", op="extract")
    finally:
        live_request.reset(door)
        recorded_request.reset(tape)
    assert calls == []
    await client.aclose()


# --- the gate and the routes ---------------------------------------------------------


@pytest.fixture
def app_and_keys(tmp_path: Path) -> Iterator[tuple[TestClient, AccessKeys]]:
    with TestClient(create_app(gated_settings(tmp_path))) as c:
        yield c, c.app.state.gate.keys  # type: ignore[attr-defined]


def _sign_in(c: TestClient, code: str) -> None:
    c.cookies.clear()
    assert c.post("/api/access", json={"code": code}).json()["granted"] is True


def _owner_records(c: TestClient) -> dict[str, int]:
    """The demo set's kind of records, made with the master code: a public item with private
    fields, a private item, a search, a project, a capture."""
    _sign_in(c, CODE)
    public = c.post(
        "/api/items",
        json={
            "item_type": "vacuum",
            "profile": "vacuum_attachment",
            "name": "Demo vacuum",
            "location": "garage shelf 3",
            "notes": "owner's own note",
        },
    ).json()["id"]
    assert c.post(f"/api/items/{public}/public", json={"public": True}).status_code == 200
    private = c.post("/api/items", json={"item_type": "drill", "notes": "secret"}).json()["id"]
    search = c.post(
        "/api/searches", json={"title": "a charger", "need_item_id": public, "profile": ""}
    )
    assert search.status_code == 201, search.text
    inventory = c.app.state.inventory  # type: ignore[attr-defined]
    project = inventory.add_project("t", "Owner project", "{}", [])["id"]
    capture = inventory.add_capture('{"note": "x"}')["id"]
    draft = inventory.add_draft(public, "sell", "{}", "[]")["id"]
    return {
        "item": public,
        "private": private,
        "search": search.json()["id"],
        "project": project,
        "capture": capture,
        "draft": draft,
    }


def test_every_write_on_the_owners_records_is_refused_for_a_judge(
    app_and_keys: tuple[TestClient, AccessKeys],
) -> None:
    c, keys = app_and_keys
    ids = _owner_records(c)
    code, _ = keys.issue("jury", scope="judge")
    _sign_in(c, code)
    names = {
        "item_id": ids["item"],
        "search_id": ids["search"],
        "project_id": ids["project"],
        "capture_id": ids["capture"],
        "draft_id": ids["draft"],
        "candidate_id": 1,
        "pack_id": 1,
    }
    creations = {(m, p.pattern) for m, p in JUDGE_CREATE}
    tried = 0
    # every route the app serves, from its schema (included routers are not flat routes)
    paths = c.app.openapi()["paths"]  # type: ignore[attr-defined]
    for route_path, operations in paths.items():
        if route_path in OPEN_PATHS:
            continue
        for method in {m.upper() for m in operations} - {"GET", "HEAD"}:
            if (method, f"^{route_path}$") in creations:
                continue
            path = re.sub(r"\{(\w+)\}", lambda m: str(names.get(m.group(1), 1)), route_path)
            answer = c.request(method, path, json={})
            tried += 1
            assert answer.status_code == 403, (method, path, answer.status_code, answer.text)
            assert answer.json()["detail"] == JUDGE_LINE
            # never the demo visitor's line: the browser keeps the session
            assert not answer.json()["detail"].startswith("demo:")
    assert tried > 50
    # nothing changed
    _sign_in(c, CODE)
    item = c.get(f"/api/items/{ids['item']}").json()
    assert item["version"] == 1 and item["notes"] == "owner's own note"


def test_a_judge_reads_the_demo_set_redacted_and_never_the_owners_private_items(
    app_and_keys: tuple[TestClient, AccessKeys],
) -> None:
    c, keys = app_and_keys
    ids = _owner_records(c)
    code, _ = keys.issue("jury", scope="judge")
    _sign_in(c, code)
    item = c.get(f"/api/items/{ids['item']}").json()
    assert item["redacted"] is True and item["location"] == "" and item["notes"] == ""
    assert [i["id"] for i in c.get("/api/items").json()] == [ids["item"]]
    assert c.get(f"/api/items/{ids['private']}").status_code == 404
    # what the visitor may not read, the judge may not either, on the owner's records
    assert c.get(f"/api/items/{ids['item']}/events").status_code == 403
    assert c.get(f"/api/captures/{ids['capture']}/clip").status_code == 403
    assert c.get("/api/spend").status_code == 403
    # an id spelled oddly is not looked up
    assert c.get("/api/items/+1").status_code == 404
    assert c.post("/api/items/01/fields", json={}).status_code == 403


def test_a_judge_works_in_a_sandbox_of_its_own(
    app_and_keys: tuple[TestClient, AccessKeys],
) -> None:
    c, keys = app_and_keys
    ids = _owner_records(c)
    jury, record = keys.issue("jury", scope="judge")
    other, _ = keys.issue("other", scope="judge")
    _sign_in(c, jury)
    made = c.post("/api/items", json={"item_type": "toaster", "notes": "my note"})
    assert made.status_code == 201
    mine = made.json()
    assert mine["owner_code"] == record.id
    # whole, editable, its history its own
    assert c.get(f"/api/items/{mine['id']}").json()["notes"] == "my note"
    patched = c.patch(f"/api/items/{mine['id']}", json={"name": "My toaster"})
    assert patched.status_code == 200 and patched.json()["name"] == "My toaster"
    assert (
        c.post(
            f"/api/items/{mine['id']}/fields", json={"field": "watts", "value": "900"}
        ).status_code
        == 200
    )
    assert c.get(f"/api/items/{mine['id']}/events").status_code == 200
    # never published
    assert c.post(f"/api/items/{mine['id']}/public", json={"public": True}).status_code == 403
    # a child of the owner's item is refused; of its own, made
    assert (
        c.post("/api/items", json={"item_type": "x", "parent_id": ids["item"]}).status_code == 403
    )
    assert c.post("/api/items", json={"item_type": "x", "parent_id": mine["id"]}).status_code == 201
    # a search for the demo item is its own and leaves the owner's history alone
    search = c.post("/api/searches", json={"title": "a lid", "need_item_id": ids["item"]})
    assert search.status_code == 201
    listed = {i["id"] for i in c.get("/api/items").json()}
    assert ids["item"] in listed and mine["id"] in listed and ids["private"] not in listed
    # another judge sees none of it
    _sign_in(c, other)
    assert mine["id"] not in {i["id"] for i in c.get("/api/items").json()}
    assert c.get(f"/api/items/{mine['id']}").status_code == 404
    assert c.delete(f"/api/items/{mine['id']}").status_code == 404
    assert c.get(f"/api/searches/{search.json()['id']}").status_code == 404
    assert search.json()["id"] not in {s["id"] for s in c.get("/api/searches").json()}
    # nor does the demo visitor
    c.cookies.clear()
    assert [i["id"] for i in c.get("/api/items").json()] == [ids["item"]]
    assert search.json()["id"] not in {s["id"] for s in c.get("/api/searches").json()}
    # the owner sees everything, the owner's history untouched by the judge's search
    _sign_in(c, CODE)
    events = c.get(f"/api/items/{ids['item']}/events").json()
    assert not any("a lid" in e["change"] for e in events)
    assert mine["id"] in {i["id"] for i in c.get("/api/items").json()}
    # and the judge deletes its own
    _sign_in(c, jury)
    assert c.delete(f"/api/items/{mine['id']}").status_code == 204


def test_a_judge_code_is_capped_before_the_route_runs(
    app_and_keys: tuple[TestClient, AccessKeys],
) -> None:
    c, keys = app_and_keys
    code, record = keys.issue("jury", scope="judge", calls_per_day=1, max_usd=1.0)
    _sign_in(c, code)
    access = c.get("/api/access").json()
    assert access["judge"] == {
        "code_id": record.id,
        "recorded": False,
        "calls_per_day": 1,
        "calls_left": 1,
        "max_usd": 1.0,
        "usd_left": 1.0,
    }
    keys.charge(record.id, 0.25)
    assert c.get("/api/access").json()["judge"]["calls_left"] == 0
    answer = c.post("/api/extract", files={"photos": ("a.jpg", b"x", "image/jpeg")})
    assert answer.status_code == 429 and answer.json()["detail"] == DAILY_CALLS_LINE
    keys.charge(record.id, 0.75)
    answer = c.post("/api/extract", files={"photos": ("a.jpg", b"x", "image/jpeg")})
    assert answer.status_code == 403 and answer.json()["detail"] == BUDGET_LINE
    # the master code is never held to a judge's limits
    _sign_in(c, CODE)
    assert c.post(
        "/api/extract", files={"photos": ("a.jpg", b"x", "image/jpeg")}
    ).status_code not in (
        403,
        429,
    )


def test_a_judge_session_hands_out_no_pairing(app_and_keys: tuple[TestClient, AccessKeys]) -> None:
    c, keys = app_and_keys
    code, _ = keys.issue("jury", scope="judge")
    _sign_in(c, code)
    web = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    answer = c.get("/api/pair", params={"origin": "http://testserver"}, headers=web)
    assert answer.status_code == 200, answer.text
    assert not answer.json().get("token")


def test_a_recorded_judge_code_reads_as_not_live(
    app_and_keys: tuple[TestClient, AccessKeys],
) -> None:
    c, keys = app_and_keys
    code, _ = keys.issue("tape", scope="judge", recorded=True)
    _sign_in(c, code)
    access = c.get("/api/access").json()
    assert access["live"] is False and access["judge"]["recorded"] is True


def test_the_contexts_are_cleared_after_each_request(
    app_and_keys: tuple[TestClient, AccessKeys],
) -> None:
    c, keys = app_and_keys
    code, _ = keys.issue("jury", scope="judge")
    _sign_in(c, code)
    c.get("/api/items")
    assert judge_code.get() == 0 and code_meter.get() is None and recorded_request.get() is False


# --- the codes outlive a demo reset ----------------------------------------------------


def test_codes_and_their_use_survive_a_reset(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path)
    with TestClient(create_app(settings)) as c:
        keys: AccessKeys = c.app.state.gate.keys  # type: ignore[attr-defined]
        code, record = keys.issue("jury", scope="judge")
        keys.charge(record.id, 0.3)
        _sign_in(c, code)
        assert c.post("/api/items", json={"item_type": "kettle"}).status_code == 201
    gone = reset(settings)
    assert "inventory.sqlite3" in gone and settings.keys_db_path.is_file()
    with TestClient(create_app(settings)) as c:
        _sign_in(c, code)  # the same code opens the door after the reset
        assert c.get("/api/items").json() == []  # its sandbox went with the inventory
        assert c.get("/api/access").json()["judge"]["usd_left"] == pytest.approx(4.7)


def test_codes_an_older_build_kept_in_the_inventory_move_to_their_own_file(
    tmp_path: Path,
) -> None:
    settings = gated_settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    # the inventory as an older build left it, with a code in it
    from app.inventory.store import Store

    Store(settings.inventory_db_path)
    with sqlite3.connect(settings.inventory_db_path) as conn:
        conn.execute(
            "INSERT INTO access_keys (id, hash, label, created_at) VALUES (7, 'h', 'old', ?)",
            ("2026-11-01T00:00:00+00:00",),
        )
    assert not settings.keys_db_path.exists()
    # a reset opens the codes' file first: the code moves before the inventory goes
    reset(settings)
    keys = AccessKeys(open_keys(settings))
    moved = keys.all()
    assert [(k.id, k.label, k.scope) for k in moved] == [(7, "old", "owner")]

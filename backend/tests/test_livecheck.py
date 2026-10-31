"""The live check (``livecheck/`` at the repository root, ``./dev live-check``) stays out of
every image and out of the app; its dry run on the recordings passes every operation and
prints no credential; its HTTP proof reads a gated host the way a browser does."""

import ast
import asyncio
import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_api import CostLedger
from app.model_api.ledger import LedgerEntry
from tests.conftest import RECORDED_FIXTURES, make_photo

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
APP = BACKEND / "app"
MODAL_APP = ROOT / "deploy" / "modal_app.py"
# beside the backend in a clone; the read-only mount in the backend container
LIVECHECK_PARENTS = [ROOT, Path("/opt/livecheck")]
IMAGE_DIRS = {"str(BACKEND / 'app')", "str(BACKEND / 'tests' / 'fixtures')", "str(ROOT / 'demo')"}
OPS = ["segment", "transcribe", "extract", "listing-text", "draft", "uses", "propose", "price"]
ALL_OPS = [*OPS, "picture"]
PLACEHOLDER_KEY = "placeholder-key-SHOULD-NOT-APPEAR"
PLACEHOLDER_CODE = "code-test-SHOULD-NOT-APPEAR-either"
GATE_CODE = "live-check-gate-code"


def _livecheck_parent() -> Path:
    for parent in LIVECHECK_PARENTS:
        if (parent / "livecheck" / "__main__.py").is_file():
            return parent
    pytest.skip("livecheck/ is not in this tree")


def _image_calls(tree: ast.AST) -> list[ast.Call]:
    """Every call that can put a local file into a Modal image or container: add_local_* and
    copy_local_* (add_local_python_source among them), and anything named Mount."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        chain = ast.unparse(func)
        if name.startswith(("add_local", "copy_local")) or "Mount" in chain:
            found.append(node)
    return found


def test_the_modal_image_takes_the_app_the_recordings_and_the_demo_set_only() -> None:
    if not MODAL_APP.is_file():
        pytest.skip("deploy/modal_app.py is not in this tree")
    source = MODAL_APP.read_text()
    assert "livecheck" not in source
    calls = _image_calls(ast.parse(source))
    assert [ast.unparse(call.func).rsplit(".", 1)[-1] for call in calls] == ["add_local_dir"] * 3
    assert {ast.unparse(call.args[0]) for call in calls} == IMAGE_DIRS
    assert len(calls) == len(IMAGE_DIRS)


class _TaggedLoader(yaml.SafeLoader):
    """Compose files carry tags such as !override; read the value under the tag."""


def _untagged(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)  # type: ignore[arg-type]


_TaggedLoader.add_multi_constructor("!", _untagged)


def _compose(name: str) -> dict[str, Any]:
    path = ROOT / name
    if not path.is_file():
        pytest.skip(f"{name} is not in this tree")
    data = yaml.load(path.read_text(), Loader=_TaggedLoader)
    assert isinstance(data, dict)
    return data


def _context(service: dict[str, Any]) -> str | None:
    build = service.get("build")
    if build is None:
        return None
    return build if isinstance(build, str) else build.get("context", ".")


@pytest.mark.parametrize("name", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_the_images_build_from_their_own_directories(name: str) -> None:
    services = _compose(name)["services"]
    contexts = {svc: _context(spec) for svc, spec in services.items()}
    assert contexts.get("backend") == "./backend"
    assert contexts.get("frontend") in (None, "./frontend")
    if name == "docker-compose.prod.yml":
        assert contexts["frontend"] == "./frontend"
    # the docs image builds from its own folder; nothing builds from the repository root
    assert {c for c in contexts.values() if c} <= {"./backend", "./frontend", "./docker/docs"}


@pytest.mark.parametrize("image", ["backend", "frontend"])
def test_the_dockerfiles_copy_nothing_from_outside_their_context(image: str) -> None:
    # the backend's own folder (the container's /app too), the frontend's beside it
    dockerfile = (BACKEND if image == "backend" else ROOT / image) / "Dockerfile"
    if not dockerfile.is_file():
        pytest.skip(f"{image}/Dockerfile is not in this tree")
    for line in dockerfile.read_text().splitlines():
        words = line.split()
        if not words or words[0].upper() not in ("COPY", "ADD"):
            continue
        if any(w.startswith("--from") for w in words):
            continue  # from another stage of the same build, not from the host
        sources = [w for w in words[1:-1] if not w.startswith("--")]
        assert not any(".." in w or w.startswith("/") for w in sources), line
        assert not any("livecheck" in w for w in words), line


def test_the_production_backend_mounts_nothing_but_its_data() -> None:
    backend = _compose("docker-compose.prod.yml")["services"]["backend"]
    volumes = [str(v) for v in backend.get("volumes", [])]
    assert not any("livecheck" in v for v in volumes)
    assert volumes == ["app-data:/data"]


def test_nothing_in_the_app_imports_the_live_check() -> None:
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(n == "livecheck" or n.startswith("livecheck.") for n in names), path


def test_the_dry_run_passes_every_operation_and_prints_no_credential(tmp_path: Path) -> None:
    parent = _livecheck_parent()
    env = {
        **os.environ,
        "OPL_FAKE_API": "1",
        "MODEL_API_KEY": PLACEHOLDER_KEY,
        "LIVECHECK_ACCESS_CODE": PLACEHOLDER_CODE,
        "DATA_DIR": str(tmp_path / "data"),
        "LOG_FORMAT": "text",
        "PYTHONPATH": str(parent),
    }
    env.pop("OPL_RECORD_FIXTURES", None)
    done = subprocess.run(
        [sys.executable, "-m", "livecheck", "--ops", ",".join(ALL_OPS)],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    output = done.stdout + done.stderr
    assert done.returncode == 0, output
    assert "SHOULD-NOT-APPEAR" not in output
    assert f"MODEL_API_KEY: set ({len(PLACEHOLDER_KEY)} chars)" in done.stdout
    rows = {
        line.split()[0]: line
        for line in done.stdout.splitlines()
        if line.split()[:1] and line.split()[0] in ALL_OPS
    }
    assert sorted(rows) == sorted(ALL_OPS), done.stdout
    assert all(" PASS " in line for line in rows.values()), done.stdout
    assert all("from_fixture=True" in line for op, line in rows.items() if op != "propose")
    n = len(ALL_OPS)
    assert f"total: {n} ops, {n} passed, 0 failed, 0 skipped, spent $0.0000" in done.stdout


def test_an_unknown_op_and_a_credential_flag_are_refused() -> None:
    parent = _livecheck_parent()
    env = {**os.environ, "OPL_FAKE_API": "1", "PYTHONPATH": str(parent)}
    for args in (
        ["--ops", "nothing"],
        ["--code", "x"],
        ["--against", "backend:8000"],
        ["--against", "http://demo.example.com"],
    ):
        done = subprocess.run(
            [sys.executable, "-m", "livecheck", *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.returncode == 2, args


def _run_livecheck(
    tmp_path: Path, extra: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "OPL_FAKE_API": "1",
        "DATA_DIR": str(tmp_path / "data"),
        "LOG_FORMAT": "text",
        "PYTHONPATH": str(_livecheck_parent()),
        **extra,
    }
    return subprocess.run(
        [sys.executable, "-m", "livecheck", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_record_mode_is_refused_even_beside_fixture_mode(tmp_path: Path) -> None:
    before = sorted(p.name for p in RECORDED_FIXTURES.rglob("*"))
    for fake in ("1", "0"):
        done = _run_livecheck(
            tmp_path,
            {"OPL_RECORD_FIXTURES": "1", "OPL_FAKE_API": fake, "MODEL_API_KEY": PLACEHOLDER_KEY},
            "--ops",
            "segment",
        )
        assert done.returncode == 2, done.stdout + done.stderr
        assert "does not record fixtures; unset OPL_RECORD_FIXTURES" in done.stderr
        assert "PASS" not in done.stdout
    assert sorted(p.name for p in RECORDED_FIXTURES.rglob("*")) == before


def test_transcribe_goes_through_the_voice_note_service(tmp_path: Path) -> None:
    # the route's own length check runs: a one-second note over a limit of none fails
    done = _run_livecheck(tmp_path, {"VOICE_MAX_SECONDS": "0"}, "--ops", "transcribe")
    assert done.returncode == 1, done.stdout + done.stderr
    row = next(line for line in done.stdout.splitlines() if line.startswith("transcribe"))
    assert " FAIL " in row and "at most 0 s" in row


def test_plain_http_reaches_this_machine_only() -> None:
    main = _module("__main__")
    for url in ("http://localhost:8000", "http://127.0.0.1:8070", "http://backend:8000"):
        assert main.against_refusal(url) == "", url
    assert main.against_refusal("https://demo.example.com") == ""
    for url in ("http://demo.example.com", "http://10.0.0.5:8000", "ftp://localhost", "https://"):
        assert main.against_refusal(url), url


def test_redaction_catches_a_secret_whole_split_or_echoed() -> None:
    report = _module("report")
    secret = "placeholder-" + "s" * 12
    out = io.StringIO()
    stream = report.Redacting(out, [secret])
    stream.write(f"key {secret} end\n")
    stream.write('{"api_key": "' + secret + '"}\n')
    # one secret over two writes on the same line
    stream.write("split " + secret[:9])
    stream.write(secret[9:] + " done\n")
    stream.write(f"tail {secret}")
    assert secret[:9] not in out.getvalue()
    stream.drain()
    text = out.getvalue()
    assert secret not in text and secret[:9] not in text
    assert text.count("***") == 4
    # echoed with JSON escapes: a secret holding a quote is still caught as JSON writes it
    quoted = 'abc"def\\ghi'
    out = io.StringIO()
    stream = report.Redacting(out, [quoted])
    stream.write(json.dumps({"k": quoted}) + "\n")
    assert "abc" not in out.getvalue()


def test_a_message_is_redacted_before_it_is_cut() -> None:
    report = _module("report")
    remote = _remote()
    secret = "placeholder-" + "c" * 20
    report._SECRETS[:] = report._forms([secret])
    try:
        # the secret straddles the cut at 157: unredacted, its head would survive the cut
        long = "x" * 150 + " " + secret + " and more after it"
        line = report.one_line(RuntimeError(long))
        assert secret[:6] not in line and "***" in line
        body = {"detail": "y" * 110 + " " + secret}
        detail = remote._detail(httpx.Response(403, json=body))
        assert secret[:6] not in detail and "***" in detail
    finally:
        report._SECRETS[:] = []


def test_the_ceilings_count_the_effort_the_attempts_and_the_search() -> None:
    ceilings = _module("ceilings")
    ops = _module("ops")
    base = Settings(OPL_FAKE_API=True, model_api_max_attempts=1)
    low = ceilings.ceiling("extract", base, audio_seconds=1.0).usd
    high = ceilings.ceiling(
        "extract", base.model_copy(update={"extract_reasoning_effort": "high"}), audio_seconds=1.0
    ).usd
    assert high > low
    four = ceilings.ceiling(
        "extract", base.model_copy(update={"model_api_max_attempts": 4}), audio_seconds=1.0
    ).usd
    assert four == pytest.approx(low * 4, rel=1e-3)
    price = ceilings.ceiling("price", base, audio_seconds=1.0)
    assert "150000 in, 18 searches" in price.why
    # the default set at the default --max-usd: the run names what it will skip up front
    defaults = Settings(OPL_FAKE_API=True)
    cs = {op: ceilings.ceiling(op, defaults, audio_seconds=1.0) for op in ops.OPS}
    beyond = [op for op in ops.OPS if cs[op].usd > 0.25]
    said = ops.plan(ops.OPS, cs, beyond, 0.25)
    if sum(c.usd for c in cs.values()) > 0.25:
        assert beyond and all(f"{op} (" in said for op in beyond)
        assert "--ops price --max-usd" in said


def test_a_live_pass_needs_a_billed_call_on_the_ledger(tmp_path: Path) -> None:
    ops = _module("ops")
    ledger = CostLedger(5.0, tmp_path / "ledger.jsonl")

    async def answered_from_a_recording(s: Any) -> str:
        ledger.record(LedgerEntry(op="probe", model="m", endpoint="/x", fixture=True))
        return "from_fixture=False"

    async def billed(s: Any) -> str:
        ledger.record(LedgerEntry(op="probe", model="m", endpoint="/x", fixture=False))
        return "from_fixture=False"

    services = SimpleNamespace(ledger=ledger)
    saved = dict(ops.CALLS)
    try:
        ops.CALLS["probe"] = answered_from_a_recording
        assert asyncio.run(ops._one(services, "probe", True)).status == "FAIL"
        assert asyncio.run(ops._one(services, "probe", False)).status == "PASS"
        ops.CALLS["probe"] = billed
        assert asyncio.run(ops._one(services, "probe", True)).status == "PASS"
    finally:
        ops.CALLS.clear()
        ops.CALLS.update(saved)


def test_a_broken_gate_has_its_probe_item_removed_and_still_fails() -> None:
    remote = _remote()
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path == "/readyz":
            return httpx.Response(200, json={"demo": {"gated": True, "live_models": False}})
        if path == "/api/access":
            return httpx.Response(200, json={"gated": True, "granted": False, "live": False})
        if path == "/api/extract":
            return httpx.Response(200, json={"fields": {}, "from_fixture": True})
        if request.method == "POST" and path == "/api/items":
            return httpx.Response(201, json={"id": 7})
        if request.method == "DELETE" and path == "/api/items/7":
            return httpx.Response(204)
        return httpx.Response(404)

    out = io.StringIO()
    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(answer)) as http:
        run = remote.run_remote(http, code="", max_usd=0.25, photo=b"x", out=out)
    write = next(r for r in run.results if r.op == "write (no code)")
    assert write.status == "FAIL"
    assert "was accepted" in write.note and "probe item 7 removed" in write.note
    assert "DELETE /api/items/7" in seen
    assert not run.ok


def _gated_settings(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        log_format="text",
        demo_access_code=GATE_CODE,
    )


def _module(name: str) -> Any:
    sys.path.insert(0, str(_livecheck_parent()))
    try:
        return importlib.import_module(f"livecheck.{name}")
    finally:
        sys.path.pop(0)


def _remote() -> Any:
    return _module("remote")


def test_the_http_proof_reads_a_gated_host_on_recordings(tmp_path: Path) -> None:
    remote = _remote()
    out = io.StringIO()
    with TestClient(create_app(_gated_settings(tmp_path))) as http:
        run = remote.run_remote(http, code=GATE_CODE, max_usd=0.25, photo=make_photo(), out=out)
    by_op = {r.op: r for r in run.results}
    assert by_op["access"].status == "PASS"
    # the visitor: a recorded answer, and no write
    assert by_op["extract (no code)"].status == "PASS", by_op["extract (no code)"].note
    assert "from_fixture=True" in by_op["extract (no code)"].note
    assert by_op["write (no code)"].status == "PASS"
    assert "HTTP 403" in by_op["write (no code)"].note
    # the code opens a session; a host on recordings has no live models behind the door,
    # which the check says rather than passes
    assert by_op["sign-in"].status == "PASS"
    assert by_op["extract"].status == "FAIL"
    assert "recordings" in by_op["extract"].note
    assert by_op["access (signed in)"].status == "FAIL"
    assert by_op["sign-out"].status == "PASS"
    assert not run.ok
    assert GATE_CODE not in out.getvalue()
    assert "LIVECHECK_ACCESS_CODE: set" in out.getvalue()


def test_the_http_proof_without_a_code_runs_the_visitor_half_only(tmp_path: Path) -> None:
    remote = _remote()
    out = io.StringIO()
    with TestClient(create_app(_gated_settings(tmp_path))) as http:
        run = remote.run_remote(http, code="", max_usd=0.25, photo=make_photo(), out=out)
    by_op = {r.op: r for r in run.results}
    assert by_op["write (no code)"].status == "PASS"
    assert by_op["sign-in"].status == "SKIP"
    assert by_op["extract"].status == "SKIP" and by_op["sign-out"].status == "SKIP"
    assert not run.ok
    assert "LIVECHECK_ACCESS_CODE: missing" in out.getvalue()

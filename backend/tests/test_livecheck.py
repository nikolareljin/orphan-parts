"""The live check (``livecheck/`` at the repository root, ``./dev live-check``) stays out of
every image and out of the app; its dry run on the recordings passes every operation and
prints no credential; its HTTP proof reads a gated host the way a browser does."""

import ast
import importlib
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
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


def test_the_modal_image_takes_the_app_the_recordings_and_the_demo_set_only() -> None:
    if not MODAL_APP.is_file():
        pytest.skip("deploy/modal_app.py is not in this tree")
    calls = [
        node
        for node in ast.walk(ast.parse(MODAL_APP.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_local_dir"
    ]
    assert {ast.unparse(call.args[0]) for call in calls} == IMAGE_DIRS
    assert len(calls) == len(IMAGE_DIRS)


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
    for args in (["--ops", "nothing"], ["--code", "x"], ["--against", "backend:8000"]):
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


def _gated_settings(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        log_format="text",
        demo_access_code=GATE_CODE,
    )


def _remote():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_livecheck_parent()))
    try:
        return importlib.import_module("livecheck.remote")
    finally:
        sys.path.pop(0)


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

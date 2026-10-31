"""The live check (``livecheck/`` at the repository root, ``./dev live-check``) stays out of
every image and out of the app; its dry run on the recordings passes every operation and
prints no credential; its HTTP proof reads a gated host the way a browser does."""

import ast
import asyncio
import importlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
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


def _node(node: yaml.Node, *keys: str) -> yaml.Node:
    for key in keys:
        assert isinstance(node, yaml.MappingNode), keys
        node = next(v for k, v in node.value if k.value == key)
    return node


def test_the_production_backend_volumes_replace_the_dev_ones() -> None:
    # compose merges the two files' volume lists unless the prod one says otherwise: without
    # the tag the dev file's mounts, the live check's among them, reach the production backend
    path = ROOT / "docker-compose.prod.yml"
    if not path.is_file():
        pytest.skip("docker-compose.prod.yml is not in this tree")
    tree = yaml.compose(path.read_text(), Loader=yaml.SafeLoader)
    assert tree is not None
    volumes = _node(tree, "services", "backend", "volumes")
    assert volumes.tag in ("!override", "!reset"), volumes.tag


def test_the_production_pair_gives_the_backend_no_live_check_mount(tmp_path: Path) -> None:
    # the pair scripts/deploy.sh brings up, as compose itself merges it; config needs no daemon
    if not (ROOT / "docker-compose.prod.yml").is_file():
        pytest.skip("docker-compose.prod.yml is not in this tree")
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is not installed")
    files = ["-f", "docker-compose.yml", "-f", "docker-compose.prod.yml"]
    env = {**os.environ, "DOCKER_CONFIG": str(tmp_path)}
    done = subprocess.run(
        [docker, "compose", *files, "config", "--format", "json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    volumes = json.loads(done.stdout)["services"]["backend"].get("volumes", [])
    sources = [str(v.get("source", "")) for v in volumes]
    assert sources and not any("livecheck" in s for s in sources), sources


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
    assert "63000 in, 4 searches" in price.why
    more = ceilings.ceiling(
        "price", base.model_copy(update={"price_max_searches": 8}), audio_seconds=1.0
    )
    assert "123000 in, 8 searches" in more.why and more.usd > price.usd
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


# A name that would hold a credential; a literal of 4 or more characters beside one is a
# hard-coded value, which no file of the live check may carry.
CREDENTIAL_NAME = re.compile(r"(code|key|token|secret|password|passwd|bearer)", re.IGNORECASE)
ENV_READS = {"get", "getenv", "setdefault"}
# Literals beside such a name that are known not to be values, each with why:
#   MODEL_API_KEY, LIVECHECK_ACCESS_CODE  the environment variables' names, never their values
#   adapter                               the demo set's stand-in item, by its item key
#                                         (inputs.demo_item); an item's name, no credential
ALLOWED_LITERALS = {"MODEL_API_KEY", "LIVECHECK_ACCESS_CODE", "adapter"}


def _literal(node: ast.AST | None) -> str:
    """A string literal of 4 or more characters that is not an allowed name, or ""."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value) >= 4
        and node.value not in ALLOWED_LITERALS
    ):
        return node.value
    return ""


def _fallbacks(node: ast.AST | None) -> list[str]:
    """The literals a value can come to: itself, either side of an or, either branch of an
    if-else."""
    if isinstance(node, ast.BoolOp):
        return [lit for value in node.values for lit in _fallbacks(value)]
    if isinstance(node, ast.IfExp):
        return _fallbacks(node.body) + _fallbacks(node.orelse)
    found = _literal(node)
    return [found] if found else []


def _is_env_read(node: ast.AST) -> bool:
    """os.environ.get, environ.get, os.getenv, getenv, (os.)environ.setdefault."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "getenv"
    if not isinstance(func, ast.Attribute) or func.attr not in ENV_READS:
        return False
    owner = ast.unparse(func.value)
    return owner in ("os", "environ", "os.environ") and (owner != "os" or func.attr == "getenv")


def _target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return str(node.slice.value)
    return ""


def _hard_coded_credentials(source: str) -> list[str]:
    """Every place in ``source`` where a credential would come from the code: an environment
    read with a default that is not empty, or a literal assigned to, annotated on, defaulted
    for, passed as or keyed by a credential's name, or or-ed with an environment read."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        pairs: list[tuple[str, ast.AST | None]] = []
        if _is_env_read(node):
            assert isinstance(node, ast.Call)
            defaults = node.args[1:] + [k.value for k in node.keywords if k.arg == "default"]
            for default in defaults:
                if not (isinstance(default, ast.Constant) and default.value == ""):
                    found.append(f"line {node.lineno}: {ast.unparse(node)}")
        elif isinstance(node, ast.BoolOp) and any(_is_env_read(v) for v in node.values):
            if _fallbacks(node):
                found.append(f"line {node.lineno}: {ast.unparse(node)}")
        if isinstance(node, ast.Assign):
            pairs += [(_target_name(t), node.value) for t in node.targets]
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            pairs.append((_target_name(node.target), node.value))
        elif isinstance(node, ast.arguments):
            positional = node.posonlyargs + node.args
            pairs += [
                (a.arg, d) for a, d in zip(positional[::-1], node.defaults[::-1], strict=False)
            ]
            pairs += [(a.arg, d) for a, d in zip(node.kwonlyargs, node.kw_defaults, strict=True)]
        elif isinstance(node, ast.keyword) and node.arg:
            pairs.append((node.arg, node.value))
        elif isinstance(node, ast.Dict):
            pairs += [
                (k.value, v)
                for k, v in zip(node.keys, node.values, strict=True)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
        for name, value in pairs:
            if CREDENTIAL_NAME.search(name) and _fallbacks(value):
                found.append(f"line {getattr(value, 'lineno', '?')}: {name} = {_fallbacks(value)}")
    return found


# each written the way it would be met, with a plain stand-in for the value
PROBE_VALUE = "plain-stand-in"
HARD_CODED = [
    source.replace("VALUE", PROBE_VALUE)
    for source in (
        'import os\ncode = os.environ.get("LIVECHECK_ACCESS_CODE", "VALUE")\n',
        'import os\nx = os.environ.get("MODEL_API_KEY", "VALUE")\n',
        'import os\nx = os.environ.get("LIVECHECK_ACCESS_CODE") or "VALUE"\n',
        'def run(code: str = "VALUE") -> None:\n    pass\n',
        'DEFAULT_CODE = "VALUE"\n',
        'import os\nkey = os.getenv("MODEL_API_KEY", default="VALUE")\n',
        'import os\nos.environ.setdefault("MODEL_API_KEY", "VALUE")\n',
        'class C:\n    def __init__(self) -> None:\n        self.token = "VALUE"\n',
        'HEADERS = {"api_key": "VALUE"}\n',
        'import os\nkey = os.environ.get("MODEL_API_KEY") if os.environ else "VALUE"\n',
        'call(access_code="VALUE")\n',
    )
]


@pytest.mark.parametrize("source", HARD_CODED)
def test_the_credential_check_catches_a_hard_coded_value(source: str) -> None:
    assert _hard_coded_credentials(source), source


def test_the_credential_check_lets_names_and_empty_defaults_through() -> None:
    source = (
        "import os\n"
        'key = os.environ.get("MODEL_API_KEY", "")\n'
        'code = os.environ.get("LIVECHECK_ACCESS_CODE")\n'
        'name = "MODEL_API_KEY"\n'
        "found = sorted(['a'], key=len)\n"
    )
    assert _hard_coded_credentials(source) == []


def test_no_file_of_the_live_check_holds_a_hard_coded_credential() -> None:
    files = sorted((_livecheck_parent() / "livecheck").rglob("*.py"))
    assert files
    for path in files:
        assert _hard_coded_credentials(path.read_text(encoding="utf-8")) == [], path


# Run main() with an op that prints the key, mid-line and on a line of its own, and raises
# with it; the op stands in for any code under main() that would print a credential.
LEAKY_RUN = """
import os, sys, time
from app.config import get_settings
from livecheck import __main__ as entry, ops

async def leaky(*args, **kwargs):
    key = get_settings().model_api_key.get_secret_value()
    print("the key is", key, "here")
    print(repr({"api_key": key}))
    sys.stdout.write("tail " + key)
    if os.environ.get("LEAKY_READY"):
        open(os.environ["LEAKY_READY"], "w").close()
        time.sleep(60)
    raise entry.RefusedError("refused over " + key)

ops.run_api = leaky
sys.exit(entry.main(["--ops", "segment"]))
"""


def _leaky_env(tmp_path: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {
        **os.environ,
        "OPL_FAKE_API": "1",
        "DATA_DIR": str(tmp_path / "data"),
        "PYTHONPATH": os.pathsep.join([str(_livecheck_parent()), str(BACKEND)]),
        **extra,
    }
    for name in ("MODEL_API_KEY", "LIVECHECK_ACCESS_CODE", "OPL_RECORD_FIXTURES", "LEAKY_READY"):
        if name not in extra:
            env.pop(name, None)
    # run outside backend/, a measured child would find no coverage settings (no branch data)
    # and spoil the combined report; this child is not measured
    for name in [n for n in env if n.startswith(("COV_CORE_", "COVERAGE_"))]:
        env.pop(name)
    return env


def _leaky(tmp_path: Path, extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # run from an empty folder: the only .env read is the one a case writes there
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, "-c", LEAKY_RUN],
        cwd=work,
        env=_leaky_env(tmp_path, extra),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _assert_redacted(done: subprocess.CompletedProcess[str]) -> None:
    output = done.stdout + done.stderr
    assert "SHOULD-NOT-APPEAR" not in output, output
    assert "the key is *** here" in done.stdout, output
    assert "{'api_key': '***'}" in done.stdout, output
    assert "live-check: refused: refused over ***" in done.stderr, output
    assert done.returncode == 2, output


def test_main_redacts_the_key_from_the_environment(tmp_path: Path) -> None:
    _assert_redacted(_leaky(tmp_path, {"MODEL_API_KEY": PLACEHOLDER_KEY}))


def test_main_redacts_the_key_the_settings_read_from_env_file(tmp_path: Path) -> None:
    # not in the environment: only the settings know it, from the .env beside the run
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / ".env").write_text(f"MODEL_API_KEY={PLACEHOLDER_KEY}\n")
    _assert_redacted(_leaky(tmp_path, {}))


def test_a_last_line_without_a_line_break_goes_out_redacted_at_exit(tmp_path: Path) -> None:
    done = _leaky(tmp_path, {"MODEL_API_KEY": PLACEHOLDER_KEY})
    assert "tail ***" in done.stdout, done.stdout + done.stderr
    assert "SHOULD-NOT-APPEAR" not in done.stdout


def test_sigterm_still_drains_the_held_line_redacted(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    work = tmp_path / "work"
    work.mkdir()
    with subprocess.Popen(
        [sys.executable, "-c", LEAKY_RUN],
        cwd=work,
        env=_leaky_env(tmp_path, {"MODEL_API_KEY": PLACEHOLDER_KEY, "LEAKY_READY": str(ready)}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as proc:
        deadline = time.monotonic() + 60
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "the op never reached its held line"
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
    assert proc.returncode == 128 + signal.SIGTERM, out + err
    assert "tail ***" in out, out + err
    assert "SHOULD-NOT-APPEAR" not in out + err


def test_the_probe_inventory_stays_in_the_temporary_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops = _module("ops")
    real = tmp_path / "real" / "inventory.sqlite3"
    monkeypatch.setattr(
        ops,
        "get_settings",
        lambda: Settings(
            OPL_FAKE_API=True, data_dir=tmp_path / "data", inventory_db_file=str(real)
        ),
    )
    work = tmp_path / "work"
    settings = ops._settings(work)
    assert settings.inventory_db_path == work / "inventory.sqlite3"

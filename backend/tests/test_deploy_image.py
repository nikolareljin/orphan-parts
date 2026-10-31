"""The image ``deploy/modal_app.py`` builds never carries a local secret file, a key or a
cache. ``modal`` is not installed here, so the list is read off the file and the patterns are
checked the way Modal's dockerignore-style matcher reads them."""

import ast
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

import pytest

MODAL_APP = Path(__file__).resolve().parents[2] / "deploy" / "modal_app.py"

EXCLUDED = [
    ".env",
    ".env.local",
    "demo/.env.local",
    "x/__pycache__/y.pyc",
    "x/__pycache__/notes.txt",
    "x/y.pyc",
    "keystore.properties",
    "android/keystore.properties",
    "certs/host.pem",
    "certs/host.key",
    "release.jks",
    "release.keystore",
]
KEPT = [
    "main.py",
    "demo/__main__.py",
    "set.yaml",
    "listings/frappe-agitator.md",
    "notes/one.txt",
    "api/responses/answer.json",
    "profiles/data/kitchen.yaml",
]


def _never_shipped() -> list[str]:
    if not MODAL_APP.is_file():
        pytest.skip("deploy/modal_app.py is not in this tree")
    for node in ast.parse(MODAL_APP.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "NEVER_SHIPPED" for target in node.targets
        ):
            patterns = ast.literal_eval(node.value)
            assert isinstance(patterns, list) and all(isinstance(p, str) for p in patterns)
            return patterns
    raise AssertionError("no NEVER_SHIPPED list in deploy/modal_app.py")


def _excluded(patterns: list[str], path: str) -> bool:
    # every pattern is **/<name>: a file or a directory of that name at any depth, and what
    # is under a matched directory goes with it
    return any(
        fnmatch(part, pattern.removeprefix("**/"))
        for pattern in patterns
        for part in PurePosixPath(path).parts
    )


def test_every_pattern_names_a_file_or_a_directory_at_any_depth() -> None:
    for pattern in _never_shipped():
        assert pattern.startswith("**/") and "/" not in pattern[3:], pattern


@pytest.mark.parametrize("path", EXCLUDED)
def test_a_secret_file_a_key_or_a_cache_is_excluded(path: str) -> None:
    assert _excluded(_never_shipped(), path)


@pytest.mark.parametrize("path", KEPT)
def test_the_code_the_recordings_and_the_demo_set_are_kept(path: str) -> None:
    assert not _excluded(_never_shipped(), path)


def test_every_directory_added_to_the_image_takes_the_list() -> None:
    _never_shipped()
    calls = [
        node
        for node in ast.walk(ast.parse(MODAL_APP.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_local_dir"
    ]
    assert len(calls) == 3
    for call in calls:
        ignores = [kw.value for kw in call.keywords if kw.arg == "ignore"]
        assert len(ignores) == 1
        assert isinstance(ignores[0], ast.Name) and ignores[0].id == "NEVER_SHIPPED"


def _source() -> str:
    if not MODAL_APP.is_file():
        pytest.skip("deploy/modal_app.py is not in this tree")
    return MODAL_APP.read_text()


def _constants(tree: ast.Module) -> dict[str, str]:
    """The module's string constants, f-strings of earlier ones included."""
    found: dict[str, str] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found[node.targets[0].id] = value.value
        elif isinstance(value, ast.JoinedStr):
            parts = []
            for part in value.values:
                if isinstance(part, ast.Constant):
                    parts.append(str(part.value))
                elif isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name):
                    parts.append(found[part.value.id])
            found[node.targets[0].id] = "".join(parts)
    return found


def _value(node: ast.expr, consts: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return consts[node.id]
    assert isinstance(node, ast.Constant) and isinstance(node.value, str)
    return node.value


def _calls(tree: ast.AST, method: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == method
    ]


def test_the_image_names_the_demo_set_it_ships(monkeypatch: pytest.MonkeyPatch) -> None:
    """The samples the demo visitor clicks come from DEMO_SET. The backend's default is the
    set beside app/ (``/root/app`` on Modal, so ``/demo``), which the image does not carry:
    the web function and load_demo set DEMO_SET to the set.yaml of the demo directory the
    image ships."""
    tree = ast.parse(_source())
    consts = _constants(tree)
    shipped = ""
    for call in _calls(tree, "add_local_dir"):
        local = ast.unparse(call.args[0])
        if local.endswith("'demo')"):
            shipped = _value(next(k.value for k in call.keywords if k.arg == "remote_path"), consts)
    assert shipped, "the image ships no demo directory"
    # web() and load_demo each set it before the app reads its settings
    values: dict[str, str] = {}
    setters = {}
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef) and fn.name in ("web", "load_demo"):
            for call in _calls(fn, "setdefault"):
                if ast.unparse(call.func) == "os.environ.setdefault":
                    name = _value(call.args[0], consts)
                    if name == "DEMO_SET":
                        setters[fn.name] = _value(call.args[1], consts)
    assert set(setters) == {"web", "load_demo"}, setters
    assert len(set(setters.values())) == 1
    values["DEMO_SET"] = setters["web"]
    assert values["DEMO_SET"] == f"{shipped}/set.yaml"
    # without it the backend's default on that image would miss the set
    default = PurePosixPath("/root/app").parent.parent / "demo" / "set.yaml"
    assert str(default) != values["DEMO_SET"]
    # and the backend reads the variable the image sets
    from app.config import Settings

    monkeypatch.setenv("DEMO_SET", values["DEMO_SET"])
    assert Settings(OPL_FAKE_API=True, _env_file=None).demo_set == Path(values["DEMO_SET"])


@pytest.mark.parametrize(
    ("key", "live", "fake"),
    [("k", False, "1"), ("k", True, None), ("", False, "1"), ("", True, "1")],
)
def test_load_demo_replays_the_recordings_unless_asked_live(
    monkeypatch: pytest.MonkeyPatch, key: str, live: bool, fake: str | None
) -> None:
    """A host with a key would answer a plain load live, at a price and with answers the
    recordings the visitor's samples replay do not hold: load_demo replays unless --live."""
    import importlib.util
    import os
    import sys
    import types

    import app.demo.__main__ as demo_main

    class Stub:
        def __getattr__(self, name: str) -> object:
            return lambda *a, **kw: self

        def function(self, **kw: object) -> object:
            return lambda f: f

    modal = types.ModuleType("modal")
    modal.App = lambda name: Stub()  # type: ignore[attr-defined]
    modal.Image = Stub()  # type: ignore[attr-defined]
    modal.Volume = Stub()  # type: ignore[attr-defined]
    modal.Secret = Stub()  # type: ignore[attr-defined]
    modal.concurrent = lambda **kw: lambda f: f  # type: ignore[attr-defined]
    modal.asgi_app = lambda **kw: lambda f: f  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", modal)
    seen: dict[str, object] = {}

    def main(args: list[str]) -> int:
        seen["fake"] = os.environ.get("OPL_FAKE_API")
        seen["args"] = args
        return 0

    monkeypatch.setattr(demo_main, "main", main)
    for name in ("OPL_FAKE_API", "DATA_DIR", "LOG_FORMAT", "SQLITE_JOURNAL_MODE", "DEMO_SET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODEL_API_KEY", key)
    spec = importlib.util.spec_from_file_location("modal_app_load_demo", MODAL_APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.load_demo(reset=False, live=live) == 0
    assert seen["fake"] == fake
    assert "--reset" not in seen["args"]  # type: ignore[operator]

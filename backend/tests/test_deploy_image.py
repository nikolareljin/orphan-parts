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

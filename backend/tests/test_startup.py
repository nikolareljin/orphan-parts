import ast
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import RECORDED_FIXTURES, SAMPLE_VALUE, make_photo


def live(tmp_path: Path, **over: object) -> Settings:
    spec: dict[str, object] = {
        "OPL_FAKE_API": False,
        "OPL_RECORD_FIXTURES": False,
        "model_api_key": SAMPLE_VALUE,
        "data_dir": tmp_path / "data",
        "fixtures_dir": RECORDED_FIXTURES,
        "log_format": "text",
        "_env_file": None,
    }
    spec.update(over)
    return Settings(**spec)  # type: ignore[arg-type]


def test_a_key_that_does_not_answer_puts_the_service_on_recorded_answers(
    tmp_path: Path, monkeypatch: object
) -> None:
    import app.main as main_module

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(401, json={"error": {"message": "key rejected"}})

    # the probe goes through the client the app builds: give that client the mock transport
    real = main_module.ModelApiClient

    class Probed(real):  # type: ignore[misc,valid-type]
        def __init__(self, settings: Settings, ledger: object, **kw: object) -> None:
            super().__init__(settings, ledger, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "ModelApiClient", Probed)  # type: ignore[attr-defined]
    with TestClient(create_app(live(tmp_path))) as c:
        ready = c.get("/readyz").json()
        assert ready["model_api"] == "fixture (key failed)"
        assert calls and calls[0].endswith("/models")
        # the reading comes from the recorded answers, nothing is sent to the key
        read = c.post("/api/extract", files=[("photos", ("a.jpg", make_photo(), "image/jpeg"))])
        assert read.status_code == 200 and read.json()["from_fixture"] is True
        assert len(calls) == 1


def test_a_busy_api_at_the_probe_keeps_live_mode(tmp_path: Path, monkeypatch: object) -> None:
    import app.main as main_module

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "busy"}})

    real = main_module.ModelApiClient

    class Probed(real):  # type: ignore[misc,valid-type]
        def __init__(self, settings: Settings, ledger: object, **kw: object) -> None:
            super().__init__(settings, ledger, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "ModelApiClient", Probed)  # type: ignore[attr-defined]
    with TestClient(create_app(live(tmp_path, model_api_max_attempts=1))) as c:
        # a 5xx, a timeout or a 429 is the API's day, not the key's: the mode stays
        assert c.get("/readyz").json()["model_api"] == "live"


def test_the_probe_can_be_turned_off(tmp_path: Path, monkeypatch: object) -> None:
    import app.main as main_module

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(401, json={"error": {"message": "key rejected"}})

    real = main_module.ModelApiClient

    class Probed(real):  # type: ignore[misc,valid-type]
        def __init__(self, settings: Settings, ledger: object, **kw: object) -> None:
            super().__init__(settings, ledger, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "ModelApiClient", Probed)  # type: ignore[attr-defined]
    with TestClient(create_app(live(tmp_path, OPL_KEY_PROBE=False))) as c:
        assert c.get("/readyz").json()["model_api"] == "live"
        assert calls == []


def test_the_modal_app_file_says_what_the_deployment_page_says() -> None:
    """The deploy file is not importable here (no modal package); its shape is checked."""
    path = Path(__file__).resolve().parents[2] / "deploy" / "modal_app.py"
    tree = ast.parse(path.read_text())
    web = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "web")
    decorators = [ast.unparse(d) for d in web.decorator_list]
    assert any(d.startswith("app.function(") for d in decorators)
    assert any(d.startswith("modal.asgi_app(") for d in decorators)
    function = next(d for d in web.decorator_list if ast.unparse(d).startswith("app.function("))
    assert isinstance(function, ast.Call)
    keywords = {k.arg: ast.unparse(k.value) for k in function.keywords}
    assert keywords["max_containers"] == "1"
    assert "scaledown_window" in keywords and "volumes" in keywords and "secrets" in keywords
    source = path.read_text()
    assert 'Volume.from_name("orphan-parts-data"' in source
    assert 'Secret.from_name("orphan-parts")' in source
    assert "data.commit()" in source


def test_the_modal_volume_is_read_back_before_writes_and_committed_after(
    tmp_path: Path, monkeypatch: object
) -> None:
    """deploy/modal_app.py imported with a stand-in for the modal package: the middleware
    reloads the Volume before a write and commits after it, reloads before a read at most
    every RELOAD_EVERY_S, and answers 503 to a write when the reload is refused."""
    import importlib.util
    import sys
    import types

    calls: list[str] = []
    refuse = {"reload": False}

    class Volume:
        @staticmethod
        def from_name(name: str, create_if_missing: bool = False) -> "Volume":
            return Volume()

        def reload(self) -> None:
            calls.append("reload")
            if refuse["reload"]:
                raise RuntimeError("open files")

        def commit(self) -> None:
            calls.append("commit")

    class Image:
        @staticmethod
        def debian_slim(**kw: object) -> "Image":
            return Image()

        def pip_install_from_pyproject(self, *a: object, **kw: object) -> "Image":
            return self

        def add_local_dir(self, *a: object, **kw: object) -> "Image":
            return self

    class App:
        def __init__(self, name: str) -> None:
            pass

        def function(self, **kw: object) -> object:
            return lambda f: f

    modal = types.ModuleType("modal")
    modal.App = App  # type: ignore[attr-defined]
    modal.Image = Image  # type: ignore[attr-defined]
    modal.Volume = Volume  # type: ignore[attr-defined]
    modal.Secret = types.SimpleNamespace(from_name=lambda name: None)  # type: ignore[attr-defined]
    modal.concurrent = lambda **kw: lambda f: f  # type: ignore[attr-defined]
    modal.asgi_app = lambda **kw: lambda f: f  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", modal)  # type: ignore[attr-defined]
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))  # type: ignore[attr-defined]
    monkeypatch.setenv("OPL_FAKE_API", "1")  # type: ignore[attr-defined]
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)  # type: ignore[attr-defined]
    monkeypatch.delenv("SQLITE_JOURNAL_MODE", raising=False)  # type: ignore[attr-defined]
    from app import config as config_module

    config_module.get_settings.cache_clear()  # read from this environment, not the cache
    path = Path(__file__).resolve().parents[2] / "deploy" / "modal_app.py"
    spec = importlib.util.spec_from_file_location("modal_app_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RELOAD_EVERY_S = 3600.0

    with TestClient(module.web()) as c:
        assert c.get("/healthz").status_code == 200
        assert calls == ["reload"]  # the first read: read back, nothing to commit
        assert c.get("/healthz").status_code == 200
        assert calls == ["reload"]  # within the window: no second reload
        calls.clear()
        made = c.post("/api/items", json={"item_type": "kettle"})
        assert made.status_code == 201 and calls == ["reload", "commit"]
        assert c.app.state.settings.sqlite_journal_mode == "DELETE"
        calls.clear()
        refuse["reload"] = True
        refused = c.post("/api/items", json={"item_type": "kettle"})
        assert refused.status_code == 503 and refused.headers["retry-after"] == "2"
        assert calls == ["reload"]  # nothing written, nothing committed
        assert c.get("/api/items").status_code == 200  # a read goes on regardless
        assert len(c.get("/api/items").json()) == 1
    config_module.get_settings.cache_clear()


def test_project_templates_are_packaged() -> None:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert '"projects/data/*.yaml"' in text and '"profiles/data/*.yaml"' in text


def test_pairing_with_the_api_origin(client: TestClient) -> None:
    found = client.get(
        "/api/pair", params={"origin": "https://site.example", "api": "https://api.example"}
    ).json()
    assert found["url"] == "https://api.example"
    assert (
        client.get(
            "/api/pair", params={"origin": "https://site.example", "api": "api.example"}
        ).status_code
        == 422
    )
    assert (
        json.loads(client.get("/api/pair", params={"origin": "https://site.example"}).text)["url"]
        == "https://site.example"
    )

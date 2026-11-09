"""The backend on Modal: one container, the inventory and the captures on a Volume, the
settings from one secret. Deployed with ``./dev deploy modal`` (``modal deploy
deploy/modal_app.py``); the web app on Cloudflare Pages calls the URL this prints.

The secret ``orphan-parts`` holds MODEL_API_KEY, DEMO_ACCESS_CODE, SPEND_CAP_USD, OPL_FAKE_API,
CORS_ORIGINS, DEMO_COOKIE_SECURE and DEMO_TRUST_PROXY (Modal's proxy forwards the visitor's
address; without the flag every visitor would share the proxy's). Without a key the service runs in fixture mode (recorded answers, nothing
spent); with a key that does not answer, the startup probe does the same and says so.
"""

import asyncio
import logging
import os
import shlex
import time
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

app = modal.App("orphan-parts")

# never in the image, wherever one turns up under the three directories: a local secret file,
# a key, a signing store, a Python cache (dockerignore patterns; the settings come from the secret)
NEVER_SHIPPED = [
    "**/.env",
    "**/.env.*",
    "**/__pycache__",
    "**/*.pyc",
    "**/*.pem",
    "**/*.key",
    "**/*.jks",
    "**/*.keystore",
    "**/keystore.properties",
]

# where the image carries the demo set: the backend's default (beside app/, so /demo here)
# is not it, so web() and load_demo set DEMO_SET to it, for the samples the demo visitor
# clicks and for the load
DEMO_DIR = "/root/demo"
DEMO_SET = f"{DEMO_DIR}/set.yaml"

# the code, the recorded answers (fixture mode replays them: without them every read would
# fail on the host) and the demo set (loaded on the host with ``load_demo`` below)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject(str(BACKEND / "pyproject.toml"))
    .add_local_dir(str(BACKEND / "app"), remote_path="/root/app", ignore=NEVER_SHIPPED)
    .add_local_dir(
        str(BACKEND / "tests" / "fixtures"),
        remote_path="/root/tests/fixtures",
        ignore=NEVER_SHIPPED,
    )
    .add_local_dir(str(ROOT / "demo"), remote_path=DEMO_DIR, ignore=NEVER_SHIPPED)
)

data = modal.Volume.from_name("orphan-parts-data", create_if_missing=True)
RELOAD_EVERY_S = 30.0  # how stale the web container's view of the Volume may be
RELOAD_RETRY_S = 0.5  # the pause before a refused reload is tried once more
RELOAD_DRAIN_S = (
    5.0  # how long a write waits for the requests in flight before a reload
)


@app.function(
    image=image,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("orphan-parts")],
    max_containers=1,  # one writer for SQLite, one counter for the demo gate
    min_containers=int(
        os.environ.get("OPL_MIN_CONTAINERS") or "1"
    ),  # no cold start while judging
    scaledown_window=900,
    timeout=120,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():  # type: ignore[no-untyped-def]
    os.environ.setdefault("DATA_DIR", "/data")
    os.environ.setdefault("LOG_FORMAT", "json")
    # the Volume is a network filesystem: SQLite's write-ahead log does not work on one
    os.environ.setdefault("SQLITE_JOURNAL_MODE", "DELETE")
    os.environ.setdefault("DEMO_SET", DEMO_SET)
    if not os.environ.get("MODEL_API_KEY"):
        os.environ["OPL_FAKE_API"] = "1"
    from starlette.middleware import Middleware
    from starlette.responses import JSONResponse

    from app.main import create_app

    fastapi_app = create_app()
    log = logging.getLogger("app.modal")
    last_reload = float("-inf")  # the first request reads back whatever the clock says
    busy = 0  # requests inside the app, bodies still streaming included
    syncing = False  # a reload is waiting for the app to go quiet, or running
    gate = asyncio.Condition()

    async def reload() -> bool:
        try:  # blocking I/O, off the loop; one more try after a moment
            try:
                await asyncio.to_thread(data.reload)
            except Exception:  # noqa: BLE001 - the Volume's own error types
                await asyncio.sleep(RELOAD_RETRY_S)
                await asyncio.to_thread(data.reload)
        except Exception as exc:  # noqa: BLE001
            log.info("volume reload refused: %s", exc)
            return False
        return True

    class VolumeSync:
        """What another container committed (``load_demo``) is read back before any write
        of this container's and within RELOAD_EVERY_S otherwise; what this container wrote
        reaches the Volume after every write request, not only on shutdown. A reload
        remounts the Volume: a request opening the database meanwhile fails with "unable to
        open database file", so a reload runs only while no other request is inside the app
        and holds new ones back until it is done. A request that finds others inside skips
        it, unless it is a write whose view is older than RELOAD_EVERY_S: that one waits up
        to RELOAD_DRAIN_S for them, then answers 503 with Retry-After rather than commit a
        stale copy of the inventory over a set loaded meanwhile."""

        def __init__(self, app):  # type: ignore[no-untyped-def]
            self.app = app

        async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
            nonlocal last_reload, busy, syncing
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            writes = scope["method"] in ("POST", "PUT", "PATCH", "DELETE")
            ok = True
            async with gate:
                await gate.wait_for(lambda: not syncing)
                stale = time.monotonic() - last_reload > RELOAD_EVERY_S
                quiet = busy == 0 and (writes or stale)
                drain = busy > 0 and writes and stale
                if quiet or drain:
                    syncing = True
                    try:
                        if drain:
                            await asyncio.wait_for(
                                gate.wait_for(lambda: busy == 0), RELOAD_DRAIN_S
                            )
                        ok = await reload()
                    except TimeoutError:
                        log.info(
                            "volume reload skipped: %d requests still running", busy
                        )
                        ok = False
                    finally:
                        syncing = False
                        gate.notify_all()
                    if ok:
                        last_reload = time.monotonic()
                if ok or not writes:
                    busy += 1
            if writes and not ok:
                refused = JSONResponse(
                    {"detail": "the host is syncing its data; try again in a moment"},
                    status_code=503,
                    headers={"Retry-After": "2"},
                )
                await refused(scope, receive, send)
                return
            try:
                await self.app(scope, receive, send)
            finally:
                if writes:
                    # whatever the outcome: a reload may commit what is on disk anyway, so
                    # the Volume is told now rather than by accident later
                    await asyncio.to_thread(data.commit)
                async with gate:
                    busy -= 1
                    gate.notify_all()

    # innermost, so the 503 still carries the CORS and request headers the outer layers add
    fastapi_app.user_middleware.append(Middleware(VolumeSync))
    return fastapi_app


@app.function(
    image=image,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("orphan-parts")],
    timeout=1800,
)
def load_demo(reset: bool = True, live: bool = False) -> int:  # type: ignore[no-untyped-def]
    """The demo set loaded into the host's inventory from the recordings shipped with the
    image, spending nothing, whatever mode the secret says:
    ``modal run deploy/modal_app.py::load_demo`` (``--no-reset`` adds to what is there;
    ``--live`` asks the models instead, at their price, when the secret holds a key).
    The web container keeps serving meanwhile and picks the set up before its next write
    and within half a minute otherwise."""
    os.environ.setdefault("DATA_DIR", "/data")
    os.environ.setdefault("LOG_FORMAT", "text")
    os.environ.setdefault("SQLITE_JOURNAL_MODE", "DELETE")
    os.environ.setdefault("DEMO_SET", DEMO_SET)
    # the recordings answer unless a live load is asked for: a live load spends and writes
    # answers the recordings (and the samples visitors click) do not hold
    if not live or not os.environ.get("MODEL_API_KEY"):
        os.environ["OPL_FAKE_API"] = "1"
    from app.demo.__main__ import main

    args = ["load", "--set", DEMO_SET]
    if reset:
        args.append("--reset")
    code = main(args)
    data.commit()
    return code


@app.function(
    image=image,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("orphan-parts")],
    timeout=120,
)
def keys(args: str = "list") -> int:  # type: ignore[no-untyped-def]
    """The access codes of the hosted demo, in their own file on its volume (kept through
    ``load_demo``): ``modal run deploy/modal_app.py::keys --args 'issue --label jury --days 10
    --scope judge --calls-per-day 20 --max-usd 5'`` (``list``, ``revoke <label>``). The code is printed once; the web container reads the record
    before its next write and within half a minute otherwise."""
    os.environ.setdefault("DATA_DIR", "/data")
    os.environ.setdefault("LOG_FORMAT", "text")
    os.environ.setdefault("SQLITE_JOURNAL_MODE", "DELETE")
    os.environ.setdefault("OPL_FAKE_API", "1")
    from app.keys.__main__ import main as keys_main

    data.reload()
    code = keys_main(shlex.split(args))
    data.commit()
    return code

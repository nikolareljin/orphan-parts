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
    # the counts and flags change only in plain code between awaits, or in a task's done
    # callback: a request cancelled at any await (a client gone, the function's timeout)
    # can neither leave the count up nor let others in while the Volume is remounted
    busy = (
        0  # requests inside, from the gate's first read to the last byte and the commit
    )
    idle = asyncio.Event()  # set while busy == 0
    idle.set()
    open_ = asyncio.Event()  # cleared while a reload runs: requests wait at the door
    open_.set()

    async def reload() -> bool:
        nonlocal last_reload
        try:  # blocking I/O, off the loop; one more try after a moment
            try:
                await asyncio.to_thread(data.reload)
            except Exception:  # noqa: BLE001 - the Volume's own error types
                await asyncio.sleep(RELOAD_RETRY_S)
                await asyncio.to_thread(data.reload)
        except Exception as exc:  # noqa: BLE001
            log.info("volume reload refused: %s", exc)
            return False
        last_reload = time.monotonic()
        return True

    def leave() -> None:
        nonlocal busy
        busy -= 1
        if busy == 0:
            idle.set()

    def enter() -> None:
        nonlocal busy
        busy += 1
        idle.clear()

    async def come_in(writes: bool) -> bool:
        """Counts the request in, reading the Volume back first when that is due; False for a
        write that may not go on. A write whose view is stale waits up to RELOAD_DRAIN_S for
        the others to finish, without holding anyone up meanwhile; refused if they did not,
        or if the Volume refused the reload."""
        deadline = time.monotonic() + RELOAD_DRAIN_S
        while True:
            while not open_.is_set():
                await open_.wait()
            stale = time.monotonic() - last_reload > RELOAD_EVERY_S
            if busy == 0 and (writes or stale):
                open_.clear()
                # a task of its own, shielded: cancelled with this request, the reload still
                # finishes, and only then does the door open again
                task = asyncio.ensure_future(reload())
                try:
                    ok = await asyncio.shield(task)
                except BaseException:
                    task.add_done_callback(lambda _: open_.set())
                    raise
                # counted in before the door opens: nobody can start another reload under it
                if ok or not writes:
                    enter()
                open_.set()
                return ok or not writes
            if not (writes and stale):
                enter()  # a read, or a write on a fresh view: on with what is mounted
                return True
            left = deadline - time.monotonic()
            try:
                if left <= 0:
                    raise TimeoutError
                await asyncio.wait_for(idle.wait(), left)
            except TimeoutError:
                log.info("volume reload skipped: %d requests still running", busy)
                return False

    class VolumeSync:
        """What another container committed (``load_demo``) is read back before any write
        of this container's and within RELOAD_EVERY_S otherwise; what this container wrote
        reaches the Volume after every write request, not only on shutdown. A reload
        remounts the Volume: a request opening a database file meanwhile fails with "unable
        to open database file", so a reload runs only while no other request is inside and
        holds new ones at the door until it is done. Outside the demo gate, which reads the
        access codes' file. A read that finds others inside skips the reload; a write whose
        view is older than RELOAD_EVERY_S waits up to RELOAD_DRAIN_S for them, then answers
        503 with Retry-After rather than commit a stale copy of the inventory over a set
        loaded meanwhile."""

        def __init__(self, app):  # type: ignore[no-untyped-def]
            self.app = app

        async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            writes = scope["method"] in ("POST", "PUT", "PATCH", "DELETE")
            if not await come_in(writes):
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
                    # the Volume is told now rather than by accident later; the request
                    # counts as inside until the commit is done, even if it is cancelled
                    commit = asyncio.ensure_future(asyncio.to_thread(data.commit))
                    commit.add_done_callback(lambda _: leave())
                    await asyncio.shield(commit)
                else:
                    leave()

    # inside CORS, so the 503 still carries its headers; outside the demo gate, which opens
    # the access codes' file and the inventory before the route does
    stack = fastapi_app.user_middleware
    at = next(
        (
            i
            for i, m in enumerate(stack)
            if getattr(m.cls, "__name__", "") == "GateMiddleware"
        ),
        len(stack),
    )
    stack.insert(at, Middleware(VolumeSync))
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

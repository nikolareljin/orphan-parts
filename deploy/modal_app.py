"""The backend on Modal: one container, the inventory and the captures on a Volume, the
settings from one secret. Deployed with ``./dev deploy modal`` (``modal deploy
deploy/modal_app.py``); the web app on Cloudflare Pages calls the URL this prints.

The secret ``orphan-parts`` holds MODEL_API_KEY, DEMO_ACCESS_CODE, SPEND_CAP_USD, OPL_FAKE_API
and CORS_ORIGINS. Without a key the service runs in fixture mode (recorded answers, nothing
spent); with a key that does not answer, the startup probe does the same and says so.
"""

import asyncio
import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

app = modal.App("orphan-parts")

# the code, the recorded answers (fixture mode replays them: without them every read would
# fail on the host) and the demo set (loaded on the host with ``load_demo`` below)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject(str(BACKEND / "pyproject.toml"))
    .add_local_dir(str(BACKEND / "app"), remote_path="/root/app")
    .add_local_dir(str(BACKEND / "tests" / "fixtures"), remote_path="/root/tests/fixtures")
    .add_local_dir(str(ROOT / "demo"), remote_path="/root/demo")
)

data = modal.Volume.from_name("orphan-parts-data", create_if_missing=True)


@app.function(
    image=image,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("orphan-parts")],
    max_containers=1,  # one writer for SQLite, one counter for the demo gate
    min_containers=int(os.environ.get("OPL_MIN_CONTAINERS") or "1"),  # no cold start while judging
    scaledown_window=900,
    timeout=120,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():  # type: ignore[no-untyped-def]
    os.environ.setdefault("DATA_DIR", "/data")
    os.environ.setdefault("LOG_FORMAT", "json")
    if not os.environ.get("MODEL_API_KEY"):
        os.environ["OPL_FAKE_API"] = "1"
    from starlette.middleware.base import BaseHTTPMiddleware

    from app.main import create_app

    fastapi_app = create_app()

    class CommitWrites(BaseHTTPMiddleware):  # type: ignore[misc]
        """What a container wrote reaches the Volume at once, not only on shutdown."""

        async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
            response = await call_next(request)
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 500:
                # the commit is blocking I/O; off the loop so other requests are not held
                await asyncio.to_thread(data.commit)
            return response

    fastapi_app.add_middleware(CommitWrites)
    return fastapi_app


@app.function(
    image=image,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("orphan-parts")],
    timeout=1800,
)
def load_demo(reset: bool = True) -> int:  # type: ignore[no-untyped-def]
    """The demo set loaded into the host's inventory, in the mode the secret says (fixture
    mode replays the recordings shipped with the image and spends nothing):
    ``modal run deploy/modal_app.py::load_demo`` (``--no-reset`` adds to what is there).
    The web container keeps serving meanwhile; it reads the new file on its next request."""
    os.environ.setdefault("DATA_DIR", "/data")
    os.environ.setdefault("LOG_FORMAT", "text")
    if not os.environ.get("MODEL_API_KEY"):
        os.environ["OPL_FAKE_API"] = "1"
    from app.demo.__main__ import main

    args = ["load", "--set", "/root/demo/set.yaml"]
    if reset:
        args.append("--reset")
    code = main(args)
    data.commit()
    return code

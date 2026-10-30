"""The backend on Modal: one container, the inventory and the captures on a Volume, the
settings from one secret. Deployed with ``./dev deploy modal`` (``modal deploy
deploy/modal_app.py``); the web app on Cloudflare Pages calls the URL this prints.

The secret ``orphan-parts`` holds MODEL_API_KEY, DEMO_ACCESS_CODE, SPEND_CAP_USD, OPL_FAKE_API
and CORS_ORIGINS. Without a key the service runs in fixture mode (recorded answers, nothing
spent); with a key that does not answer, the startup probe does the same and says so.
"""

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

app = modal.App("orphan-parts")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject(str(BACKEND / "pyproject.toml"))
    .add_local_dir(str(BACKEND / "app"), remote_path="/root/app")
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
                data.commit()
            return response

    fastapi_app.add_middleware(CommitWrites)
    return fastapi_app

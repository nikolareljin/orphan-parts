"""Command line: python -m livecheck [--ops a,b,...] [--max-usd N] [--against URL] [--keep-going]

Run it as ``./dev live-check``, which puts it in the backend image with livecheck/ mounted
read-only and the settings the backend has. Without --against, each operation is called once
through the product's services (the api mode); with --against, the proof runs over HTTP
against the backend at that URL. OPL_FAKE_API=1 replays the recordings and spends nothing.

Exit code: 0 when every step run passed (an op whose ceiling alone is above --max-usd is named
before the run and skipped), 1 otherwise, 2 when the run was refused.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from types import FrameType
from urllib.parse import urlsplit

import httpx

from app.config import get_settings
from livecheck import inputs, ops, remote
from livecheck.report import RefusedError, install_redaction

DEFAULT_MAX_USD = 0.25


# the hosts plain http may reach: this machine, and the backend service inside the compose network
PLAIN_HTTP_HOSTS = {"localhost", "127.0.0.1", "backend"}


def against_refusal(url: str) -> str:
    """Why ``url`` is not a backend to run the HTTP proof against, or "" when it is: https
    anywhere, plain http only on this machine or to the compose service, since the session
    token travels in a header."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "--against needs an http:// or https:// URL"
    if parts.scheme == "http" and parts.hostname not in PLAIN_HTTP_HOSTS:
        return (
            f"--against {parts.hostname} over plain http: https only, but for"
            f" {', '.join(sorted(PLAIN_HTTP_HOSTS))}"
        )
    return ""


def _secrets() -> list[str]:
    """Every credential the run may hold: the two names in the environment and the key the
    settings read (from .env too); a settings refusal leaves the environment's alone."""
    found = [os.environ.get("MODEL_API_KEY", ""), os.environ.get("LIVECHECK_ACCESS_CODE", "")]
    try:
        key = get_settings().model_api_key
    except ValueError:
        key = None
    if key is not None:
        found.append(key.get_secret_value())
    return found


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m livecheck", description=__doc__)
    parser.add_argument(
        "--ops",
        default="",
        help=f"comma separated, default {','.join(ops.OPS)}; {ops.PICTURE} only when named",
    )
    parser.add_argument(
        "--max-usd",
        type=float,
        default=DEFAULT_MAX_USD,
        help=f"stop before an op that could take the run past this (default {DEFAULT_MAX_USD})",
    )
    parser.add_argument("--against", default="", help="a backend's URL: the HTTP mode")
    parser.add_argument(
        "--keep-going", action="store_true", help="go on after a failed or skipped operation"
    )
    args = parser.parse_args(argv)
    if args.max_usd < 0:
        parser.error("--max-usd must not be negative")
    chosen = [o.strip() for o in args.ops.split(",") if o.strip()]
    unknown = [o for o in chosen if o not in ops.ALL_OPS]
    if unknown:
        parser.error(f"unknown op {', '.join(unknown)}; known: {', '.join(ops.ALL_OPS)}")
    if args.against and chosen:
        parser.error("--ops applies to the api mode; --against runs the HTTP proof as it is")
    if args.against:
        why = against_refusal(args.against)
        if why:
            parser.error(why)
    args.ops = chosen or list(ops.OPS)
    return args


def _terminated(signum: int, frame: FrameType | None) -> None:
    """SIGTERM (docker stop, a killed compose run) as an ordinary exit: the redacting streams
    drain their last line at exit, which a signal's default action would skip."""
    sys.exit(128 + signum)


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    # the code from the environment and nowhere else; whatever prints a credential is cut
    code = os.environ.get("LIVECHECK_ACCESS_CODE", "")
    install_redaction(_secrets())
    signal.signal(signal.SIGTERM, _terminated)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.against:
            base = inputs.demo_dir()
            photo, _ = inputs.label_photo(base, inputs.demo_item(base))
            with httpx.Client(
                base_url=args.against, timeout=httpx.Timeout(120.0, connect=10.0)
            ) as http:
                run = remote.run_remote(
                    http, code=code, max_usd=args.max_usd, photo=photo, out=sys.stdout
                )
        else:
            run = asyncio.run(ops.run_api(args.ops, args.max_usd, args.keep_going, sys.stdout))
    except RefusedError as exc:
        print(f"live-check: refused: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        # the settings' own refusal (a missing key in live mode); its text names no value
        print(f"live-check: {exc}", file=sys.stderr)
        return 2
    except httpx.HTTPError as exc:
        print(f"live-check: {args.against}: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    return 0 if run.ok else 1


if __name__ == "__main__":
    sys.exit(main())

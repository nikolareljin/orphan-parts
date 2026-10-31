"""Command line: python -m livecheck [--ops a,b,...] [--max-usd N] [--against URL] [--keep-going]

Run it as ``./dev live-check``, which puts it in the backend image with livecheck/ mounted
read-only and the settings the backend has. Without --against, each operation is called once
through the product's services (the api mode); with --against, the proof runs over HTTP
against the backend at that URL. OPL_FAKE_API=1 replays the recordings and spends nothing.

Exit code: 0 when every selected step passed, 1 otherwise, 2 when the run was refused.
"""

import argparse
import asyncio
import logging
import os
import sys

import httpx

from livecheck import inputs, ops, remote
from livecheck.report import RefusedError, install_redaction

DEFAULT_MAX_USD = 0.25


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
    if args.against and not args.against.startswith(("http://", "https://")):
        parser.error("--against needs an http:// or https:// URL")
    args.ops = chosen or list(ops.OPS)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    # the two credentials, from the environment and nowhere else; whatever prints them is cut
    key = os.environ.get("MODEL_API_KEY", "")
    code = os.environ.get("LIVECHECK_ACCESS_CODE", "")
    install_redaction([key, code])
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

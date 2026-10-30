"""Command line: python -m app.pairing --origin http://192.168.1.20:5173 [--json]

Prints the pairing QR for the phone (or the payload as JSON with --json), with a session when
DEMO_ACCESS_CODE is set, from the same settings the service runs with.
"""

import sys

from app.config import get_settings
from app.ops.gate import Gate
from app.pairing import BadOriginError, pairing, terminal


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    origin = ""
    as_json = False
    while args:
        arg = args.pop(0)
        if arg == "--origin" and args:
            origin = args.pop(0)
        elif arg == "--json":
            as_json = True
        else:
            print(__doc__, file=sys.stderr)
            return 2
    if not origin:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        found = pairing(origin, Gate(get_settings()))
    except BadOriginError as exc:
        print(f"pairing: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(found.model_dump_json())
    else:
        print(terminal(found))
        print(
            f"{found.url}"
            + ("  (with a session for the demo)" if found.gated else "  (no code needed)")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

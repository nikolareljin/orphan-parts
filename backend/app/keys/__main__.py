"""Issue, list and revoke access codes: ``python -m app.keys issue --label judges --days 7``
prints the code once; ``list`` shows every record and its state; ``revoke <label>`` ends one.
``./dev keys`` runs this inside the backend container against the inventory file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.config import get_settings
from app.inventory.store import Store
from app.keys.service import AccessKeyError, AccessKeys


def main(argv: Sequence[str] | None = None, keys: AccessKeys | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.keys", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue", help="a new code, shown once")
    issue.add_argument("--label", required=True, help="who the code is for, e.g. judges")
    issue.add_argument("--days", type=int, default=None, help="days until it expires; none = never")
    sub.add_parser("list", help="every code with its label, dates and state")
    revoke = sub.add_parser("revoke", help="end the current code with this label")
    revoke.add_argument("label")
    args = parser.parse_args(argv)
    keys = keys or AccessKeys(Store(get_settings().inventory_db_path))
    try:
        if args.command == "issue":
            code, key = keys.issue(args.label, args.days)
            until = f"until {key.expires_at}" if key.expires_at else "with no expiry"
            print(f"{key.label}: {code}")
            print(f"issued {until}; shown once, kept as a hash", file=sys.stderr)
        elif args.command == "list":
            rows = keys.all()
            if not rows:
                print("no codes issued")
            for key in rows:
                print(
                    f"{key.id}\t{key.label}\t{key.state()}\tissued {key.created_at}"
                    f"\texpires {key.expires_at or 'never'}"
                    + (f"\trevoked {key.revoked_at}" if key.revoked_at else "")
                )
        else:
            key = keys.revoke(args.label)
            print(f"{key.label}: revoked at {key.revoked_at}")
    except AccessKeyError as exc:
        print(f"keys: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

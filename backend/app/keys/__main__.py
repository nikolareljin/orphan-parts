"""Issue, list and revoke access codes: ``python -m app.keys issue --label judges --days 7``
prints the code once; ``list`` shows every record, its scope, use and state; ``revoke <label>``
ends one. ``--scope judge`` issues a judge's code: read-only on the demo set, a sandbox of its
own, ``--calls-per-day`` live calls a day and ``--max-usd`` dollars in all (``--recorded``:
the recorded answers only). ``./dev keys`` runs this inside the backend container against the
codes' own file (KEYS_DB_FILE), which a demo reset keeps."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.config import get_settings
from app.keys.service import (
    JUDGE_CALLS_PER_DAY,
    JUDGE_MAX_USD,
    SCOPES,
    AccessKey,
    AccessKeyError,
    AccessKeys,
    Usage,
    master_tag,
)
from app.keys.store import open_keys


def main(argv: Sequence[str] | None = None, keys: AccessKeys | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.keys", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue", help="a new code, shown once")
    issue.add_argument("--label", required=True, help="who the code is for, e.g. judges")
    issue.add_argument("--days", type=int, default=None, help="days until it expires; none = never")
    issue.add_argument(
        "--scope",
        choices=SCOPES,
        default="owner",
        help="owner: the master code's full access (default); judge: read-only on the demo"
        " set, a sandbox of its own, capped",
    )
    issue.add_argument(
        "--calls-per-day",
        type=int,
        default=None,
        help=f"judge: live model calls per UTC day (default {JUDGE_CALLS_PER_DAY})",
    )
    issue.add_argument(
        "--max-usd",
        type=float,
        default=None,
        help=f"judge: dollars of live calls in all (default {JUDGE_MAX_USD:.2f})",
    )
    issue.add_argument(
        "--recorded", action="store_true", help="judge: the recorded answers only, never live"
    )
    sub.add_parser("list", help="every code with its label, scope, use, dates and state")
    revoke = sub.add_parser("revoke", help="end the current code with this label")
    revoke.add_argument("label")
    args = parser.parse_args(argv)
    if keys is None:
        settings = get_settings()
        code = settings.demo_access_code.get_secret_value() if settings.demo_access_code else ""
        keys = AccessKeys(open_keys(settings), master_tag(code))
    try:
        if args.command == "issue":
            code, key = keys.issue(
                args.label,
                args.days,
                scope=args.scope,
                recorded=args.recorded,
                calls_per_day=args.calls_per_day,
                max_usd=args.max_usd,
            )
            until = f"until {key.expires_at}" if key.expires_at else "with no expiry"
            print(f"{key.label}: {code}")
            print(f"issued {until}, {limits(key)}; shown once, kept as a hash", file=sys.stderr)
        elif args.command == "list":
            rows = keys.all()
            used = keys.usages()
            if not rows:
                print("no codes issued")
            for key in rows:
                print(
                    f"{key.id}\t{key.label}\t{key.scope}\t{key.state()}"
                    f"\t{usage(key, used.get(key.id, Usage()))}"
                    f"\tissued {key.created_at}\texpires {key.expires_at or 'never'}"
                    + (f"\trevoked {key.revoked_at}" if key.revoked_at else "")
                    + (f"\tpaired by #{key.parent_id}" if key.parent_id else "")
                    + ("\tpaired by the master code" if key.master else "")
                )
        else:
            key = keys.revoke(args.label)
            print(f"{key.label}: revoked at {key.revoked_at}")
    except AccessKeyError as exc:
        print(f"keys: {exc}", file=sys.stderr)
        return 2
    return 0


def limits(key: AccessKey) -> str:
    """What the code may do, in a few words."""
    if not key.judge:
        return "owner scope (full access)"
    if key.recorded:
        return "judge scope, recorded answers only"
    calls = "no daily cap" if key.calls_per_day is None else f"{key.calls_per_day} calls a day"
    usd = "no dollar cap" if key.max_usd is None else f"${key.max_usd:.2f} in all"
    return f"judge scope, {calls}, {usd}"


def usage(key: AccessKey, used: Usage) -> str:
    """Calls today and dollars spent, against the caps: ``calls 3/20 today  $0.41/$5.00``."""
    calls = (
        f"{used.calls_today}/{key.calls_per_day}"
        if key.calls_per_day is not None
        else str(used.calls_today)
    )
    usd = f"${used.usd:.2f}/${key.max_usd:.2f}" if key.max_usd is not None else f"${used.usd:.2f}"
    tail = " recorded" if key.recorded else ""
    return f"calls {calls} today\t{usd}{tail}"


if __name__ == "__main__":
    sys.exit(main())

"""Access codes as records: issued by a command and shown once, kept only as a hash with a
label and an expiry, revoked by label. The configured ``DEMO_ACCESS_CODE`` stays the master
code beside them; a code of either kind opens the live door.

An issued code has a scope. ``owner`` (every code issued before scopes, and the default) is
the master code's full access. ``judge`` reads the demo set as the public demo does, read-only,
keeps what it makes apart (tagged with its id) and is capped: so many live calls per UTC day
and so many dollars in all, counted on every call that bills; ``recorded`` keeps it on the
recorded answers, never a live call."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.inventory.store import Store
from app.model_api.errors import CodeLimitError

PREFIX = "opl_"
LABEL_MAX = 60
State = Literal["current", "expired", "revoked", "ended"]
Scope = Literal["owner", "judge"]
SCOPES: tuple[Scope, ...] = ("owner", "judge")
# a judge's code when the command names no limits: a day of trying things, a few dollars
JUDGE_CALLS_PER_DAY = 20
JUDGE_MAX_USD = 5.0
# A call under way, sent and not yet charged, counts as one of the day's calls and as this many
# dollars until its cost is known: two calls at once from one code never both pass the last
# check. A hold not settled in HOLD_SECONDS (a call whose answer was lost) is let go.
HOLD_USD = 0.05
HOLD_SECONDS = 600.0
DAILY_CALLS_LINE = "this code's daily calls are used; more tomorrow (UTC)"
BUDGET_LINE = "this code's budget is spent"


class AccessKeyError(ValueError):
    """A label that is blank, taken or unknown; a day count below one."""


class AccessKey(BaseModel):
    id: int
    label: str = Field(max_length=LABEL_MAX)
    created_at: str
    expires_at: str | None
    revoked_at: str | None
    # a phone's code: the issued record that paired it, or whether the master code did
    parent_id: int | None = None
    master: bool = False
    # a phone's code whose parent was revoked or expired, or whose master code changed
    ended: bool = False
    scope: Scope = "owner"
    # answered from the recorded answers only: never a live call
    recorded: bool = False
    calls_per_day: int | None = None
    max_usd: float | None = None

    @property
    def judge(self) -> bool:
        return self.scope == "judge"

    def state(self, now: datetime | None = None) -> State:
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= _text(now or datetime.now(UTC)):
            return "expired"
        return "ended" if self.ended else "current"


class Usage(BaseModel):
    """What a code has used: live calls today (UTC) and dollars in all."""

    calls_today: int = 0
    usd: float = 0.0


def refusal(key: AccessKey, used: Usage) -> CodeLimitError | None:
    """Why this code may not make another live call, or None. The calls run out for the day
    (429, again tomorrow); the dollars for good (403, until the owner issues another)."""
    if key.max_usd is not None and used.usd >= key.max_usd:
        return CodeLimitError(BUDGET_LINE, status=403)
    if key.calls_per_day is not None and used.calls_today >= key.calls_per_day:
        return CodeLimitError(DAILY_CALLS_LINE, status=429)
    return None


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def new_code() -> str:
    """A code nobody can guess: the prefix names it as ours, the rest is 24 random bytes."""
    return PREFIX + secrets.token_urlsafe(24)


def digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def master_tag(code: str) -> str:
    """What a phone's record keeps of the master code it was claimed under: enough to tell a
    rotated code, and slow to guess the code from (eight bytes of a salted PBKDF2)."""
    if not code:
        return ""
    tag = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), b"opl-phone-master", 200_000)
    return tag[:8].hex()


def _text(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


# A phone's record stands only while what paired it does: its issued parent unrevoked and
# unexpired, or the master code it was claimed under still the configured one. ``k`` is the
# record, ``p`` its parent joined on parent_id; the two parameters are now and the master tag.
_PARENT_STANDS = (
    "(k.parent_id IS NULL OR (p.id IS NOT NULL AND p.revoked_at IS NULL"
    " AND (p.expires_at IS NULL OR p.expires_at > ?)))"
    " AND (k.master IS NULL OR k.master = ?)"
)
_WITH_PARENT = "FROM access_keys k LEFT JOIN access_keys p ON p.id = k.parent_id"


class AccessKeys:
    def __init__(self, store: Store, master: str = "") -> None:
        self.store = store
        # the tag of the configured master code (master_tag), so a phone claimed under an
        # earlier one is refused; empty when there is no master code
        self.master = master
        # the calls under way per code, by when each was let through (this process's own)
        self._held: dict[int, list[float]] = {}
        self._held_lock = threading.Lock()

    def issue(
        self,
        label: str,
        days: int | None = None,
        *,
        scope: Scope = "owner",
        recorded: bool = False,
        calls_per_day: int | None = None,
        max_usd: float | None = None,
    ) -> tuple[str, AccessKey]:
        """A new code for ``label``, shown once; ``days`` from now it stops working, or never
        when not given. A judge's code gets the limits given, or the defaults; an owner's
        takes none. Returns the code and its record."""
        label = _checked(label, days)
        if scope not in SCOPES:
            raise AccessKeyError(f"the scope is one of {', '.join(SCOPES)}")
        if scope == "owner":
            if recorded or calls_per_day is not None or max_usd is not None:
                raise AccessKeyError(
                    "an owner's code is the master's full access: --recorded, --calls-per-day"
                    " and --max-usd go with --scope judge"
                )
        else:
            calls_per_day = JUDGE_CALLS_PER_DAY if calls_per_day is None else calls_per_day
            max_usd = JUDGE_MAX_USD if max_usd is None else max_usd
            if calls_per_day < 0:
                raise AccessKeyError("calls per day must be 0 or more")
            if max_usd < 0:
                raise AccessKeyError("the dollar cap must be 0 or more")
        now = datetime.now(UTC)
        expires = _text(now + timedelta(days=days)) if days is not None else None
        with self.store.connect() as conn:
            return _insert(
                conn,
                label,
                now,
                expires,
                scope=scope,
                recorded=recorded,
                calls_per_day=calls_per_day,
                max_usd=max_usd,
            )

    def issue_child(
        self, label: str, days: int, *, parent: int = 0, stamp: str = "", most: int = 0
    ) -> tuple[str, AccessKey]:
        """A phone's code, claimed with a pairing session: ``parent`` is the issued record the
        session came from (``stamp`` its issue time, as signed into the session), or 0 for
        the master code. It lasts ``days`` and never past its parent, and stands only while
        the parent does. The label may never have been used, revoked and expired records
        included, so one pairing claims once. With ``most`` set, a parent holding that many
        current phone codes pairs no more until one is revoked or runs out. The parent is
        read, its phones counted and the record written in one write transaction: a revoke
        from the command line lands before or after, never between."""
        label = _checked(label, days)
        now = datetime.now(UTC)
        until = now + timedelta(days=days)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            master: str | None = None
            if parent:
                row = conn.execute("SELECT * FROM access_keys WHERE id = ?", (parent,)).fetchone()
                found = _key_of(row) if row is not None else None
                if found is None or found.created_at != stamp or found.state(now) != "current":
                    raise AccessKeyError("the code that paired this phone has ended")
                if found.parent_id is not None or found.master:
                    raise AccessKeyError(
                        "a phone's own code does not pair another phone; pair from a page"
                        " signed in with the code you were given"
                    )
                if found.judge:
                    raise AccessKeyError("a judge's code does not pair a phone")
                if found.expires_at is not None:
                    until = min(until, datetime.fromisoformat(found.expires_at))
            else:
                if not self.master:
                    raise AccessKeyError("no master code is set")
                master = self.master
            if conn.execute("SELECT 1 FROM access_keys WHERE label = ?", (label,)).fetchone():
                raise AccessKeyError(f"a code was issued for {label!r} already")
            if most:
                paired = conn.execute(
                    "SELECT COUNT(*) FROM access_keys WHERE revoked_at IS NULL"
                    " AND (expires_at IS NULL OR expires_at > ?)"
                    " AND (parent_id = ? OR (parent_id IS NULL AND master = ?))",
                    (_text(now), parent or None, master),
                ).fetchone()[0]
                if paired >= most:
                    raise AccessKeyError(
                        f"this code has paired {paired} phones already;"
                        " revoke one with ./dev keys revoke"
                    )
            return _insert(conn, label, now, _text(until), parent or None, master)

    def all(self) -> list[AccessKey]:
        now = _text(datetime.now(UTC))
        with self.store.connect() as conn:
            rows = conn.execute(
                f"SELECT k.*, NOT ({_PARENT_STANDS}) AS ended {_WITH_PARENT} ORDER BY k.id",
                (now, self.master),
            ).fetchall()
        return [_key_of(r) for r in rows]

    def revoke(self, label: str) -> AccessKey:
        """The newest unrevoked code with this label stops working now, with every session it
        opened and every phone code it paired."""
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM access_keys WHERE label = ? AND revoked_at IS NULL"
                " ORDER BY id DESC LIMIT 1",
                (label,),
            ).fetchone()
            if row is None:
                raise AccessKeyError(f"no current code is labeled {label!r}")
            at = _text(datetime.now(UTC))
            conn.execute("UPDATE access_keys SET revoked_at = ? WHERE id = ?", (at, row["id"]))
            row = conn.execute("SELECT * FROM access_keys WHERE id = ?", (row["id"],)).fetchone()
        return _key_of(row)

    def stamp(self, kid: int) -> str | None:
        """The record's issue time when it stands unrevoked (and, for a phone's record, its
        parent too), else None (one indexed read; the gate asks on every request carrying the
        record's id, and signs the time into the session so that a record with the same id
        in another file is another record)."""
        found = self.current(kid)
        return found.created_at if found is not None else None

    def current(self, kid: int) -> AccessKey | None:
        """The record when it stands unrevoked (and its parent too), else None: what stamp
        reads, with the scope and limits the gate holds the request to."""
        now = _text(datetime.now(UTC))
        with self.store.connect() as conn:
            row = conn.execute(
                f"SELECT k.* {_WITH_PARENT}"
                f" WHERE k.id = ? AND k.revoked_at IS NULL AND {_PARENT_STANDS}",
                (kid, now, self.master),
            ).fetchone()
        return _key_of(row) if row is not None else None

    # --- what a code has used ------------------------------------------------

    def usage(self, kid: int) -> Usage:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(usd), 0) AS usd,"
                " COALESCE(SUM(CASE WHEN day = ? THEN calls END), 0) AS today"
                " FROM key_usage WHERE key_id = ?",
                (_today(), kid),
            ).fetchone()
        return Usage(calls_today=int(row["today"]), usd=round(float(row["usd"]), 6))

    def usages(self) -> dict[int, Usage]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT key_id, COALESCE(SUM(usd), 0) AS usd,"
                " COALESCE(SUM(CASE WHEN day = ? THEN calls END), 0) AS today"
                " FROM key_usage GROUP BY key_id",
                (_today(),),
            ).fetchall()
        return {
            int(r["key_id"]): Usage(calls_today=int(r["today"]), usd=round(float(r["usd"]), 6))
            for r in rows
        }

    def check(self, kid: int) -> None:
        """Raise CodeLimitError when this code may not make another live call now: read
        before each call that bills, so a code at its limit sends nothing."""
        key = self.current(kid)
        if key is None:
            raise CodeLimitError("this code has ended", status=403)
        found = refusal(key, self.usage(kid))
        if found is not None:
            raise found

    def hold(self, kid: int) -> None:
        """``check``, counting the calls still under way: let through, the call is held
        against the code (one call, HOLD_USD) until ``settle``. Raises CodeLimitError."""
        with self._held_lock:
            now = time.monotonic()
            held = [t for t in self._held.get(kid, []) if now - t < HOLD_SECONDS]
            key = self.current(kid)
            if key is None:
                raise CodeLimitError("this code has ended", status=403)
            used = self.usage(kid)
            pending = Usage(
                calls_today=used.calls_today + len(held), usd=used.usd + HOLD_USD * len(held)
            )
            found = refusal(key, pending)
            if found is not None:
                raise found
            held.append(now)
            self._held[kid] = held

    def settle(self, kid: int) -> None:
        """One call held for this code is over (charged, or never billed)."""
        with self._held_lock:
            held = self._held.get(kid)
            if held:
                held.pop(0)

    def charge(self, kid: int, usd: float) -> None:
        """One live call, at what it cost, on today's line of this code."""
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO key_usage (key_id, day, calls, usd) VALUES (?, ?, 1, ?)"
                " ON CONFLICT (key_id, day) DO UPDATE SET calls = calls + 1, usd = usd + ?",
                (kid, _today(), usd, usd),
            )

    def match(self, code: str) -> AccessKey | None:
        """The current record this code belongs to, or None. Every record is compared, in
        constant time each, so the answer takes as long for a miss as for a hit."""
        if not code.startswith(PREFIX):
            return None
        given = digest(code)
        found: AccessKey | None = None
        for key, kept in self._current():
            if hmac.compare_digest(given, kept):
                found = key
        return found

    def _current(self) -> list[tuple[AccessKey, str]]:
        now = _text(datetime.now(UTC))
        with self.store.connect() as conn:
            rows = conn.execute(
                f"SELECT k.* {_WITH_PARENT} WHERE k.revoked_at IS NULL"
                f" AND (k.expires_at IS NULL OR k.expires_at > ?) AND {_PARENT_STANDS}",
                (now, now, self.master),
            ).fetchall()
        return [(_key_of(row), str(row["hash"])) for row in rows]


def _checked(label: str, days: int | None) -> str:
    label = label.strip()
    if not label:
        raise AccessKeyError("the label is blank")
    if len(label) > LABEL_MAX:
        raise AccessKeyError(f"the label is longer than {LABEL_MAX} characters")
    if days is not None and days < 1:
        raise AccessKeyError("days must be at least 1")
    return label


def _insert(
    conn: sqlite3.Connection,
    label: str,
    now: datetime,
    expires: str | None,
    parent_id: int | None = None,
    master: str | None = None,
    *,
    scope: Scope = "owner",
    recorded: bool = False,
    calls_per_day: int | None = None,
    max_usd: float | None = None,
) -> tuple[str, AccessKey]:
    """A new record on this connection, unless a current one has the label."""
    taken = conn.execute(
        "SELECT 1 FROM access_keys WHERE label = ? AND revoked_at IS NULL"
        " AND (expires_at IS NULL OR expires_at > ?)",
        (label, _text(now)),
    ).fetchone()
    if taken:
        raise AccessKeyError(f"a current code is labeled {label!r}; revoke it first")
    code = new_code()
    cur = conn.execute(
        "INSERT INTO access_keys (hash, label, created_at, expires_at, parent_id, master,"
        " scope, recorded, calls_per_day, max_usd) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            digest(code),
            label,
            _text(now),
            expires,
            parent_id,
            master,
            scope,
            int(recorded),
            calls_per_day,
            max_usd,
        ),
    )
    row = conn.execute("SELECT * FROM access_keys WHERE id = ?", (cur.lastrowid,)).fetchone()
    return code, _key_of(row)


def _scope(value: object) -> Scope:
    """A scope this build does not know is held to the narrower one."""
    return "owner" if value == "owner" else "judge"


def _key_of(row: sqlite3.Row) -> AccessKey:
    names = row.keys()
    return AccessKey(
        id=int(row["id"]),
        label=str(row["label"]),
        created_at=str(row["created_at"]),
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        parent_id=row["parent_id"],
        master=row["master"] is not None,
        ended="ended" in names and bool(row["ended"]),
        scope=_scope(row["scope"]) if "scope" in names else "owner",
        recorded="recorded" in names and bool(row["recorded"]),
        calls_per_day=row["calls_per_day"] if "calls_per_day" in names else None,
        max_usd=row["max_usd"] if "max_usd" in names else None,
    )

"""Access codes as records: issued by a command and shown once, kept only as a hash with a
label and an expiry, revoked by label. The configured ``DEMO_ACCESS_CODE`` stays the master
code beside them; a code of either kind opens the live door."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.inventory.store import Store

PREFIX = "opl_"
LABEL_MAX = 60
State = Literal["current", "expired", "revoked", "ended"]


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

    def state(self, now: datetime | None = None) -> State:
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= _text(now or datetime.now(UTC)):
            return "expired"
        return "ended" if self.ended else "current"


def new_code() -> str:
    """A code nobody can guess: the prefix names it as ours, the rest is 24 random bytes."""
    return PREFIX + secrets.token_urlsafe(24)


def digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def master_tag(code: str) -> str:
    """What a phone's record keeps of the master code it was claimed under: enough to tell a
    rotated code, nothing to recover it from."""
    return hashlib.sha256(b"opl-phone:" + code.encode("utf-8")).hexdigest()[:16] if code else ""


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

    def issue(self, label: str, days: int | None = None) -> tuple[str, AccessKey]:
        """A new code for ``label``, shown once; ``days`` from now it stops working, or never
        when not given. Returns the code and its record."""
        label = _checked(label, days)
        now = datetime.now(UTC)
        expires = _text(now + timedelta(days=days)) if days is not None else None
        with self.store.connect() as conn:
            return _insert(conn, label, now, expires)

    def issue_child(
        self, label: str, days: int, *, parent: int = 0, stamp: str = ""
    ) -> tuple[str, AccessKey]:
        """A phone's code, claimed with a pairing session: ``parent`` is the issued record the
        session came from (``stamp`` its issue time, as signed into the session), or 0 for
        the master code. It lasts ``days`` and never past its parent, and stands only while
        the parent does. The label may never have been used, revoked and expired records
        included, so one pairing claims once. The parent is read and the record written in
        one write transaction: a revoke from the command line lands before or after, never
        between."""
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
                if found.expires_at is not None:
                    until = min(until, datetime.fromisoformat(found.expires_at))
            else:
                if not self.master:
                    raise AccessKeyError("no master code is set")
                master = self.master
            if conn.execute("SELECT 1 FROM access_keys WHERE label = ?", (label,)).fetchone():
                raise AccessKeyError(f"a code was issued for {label!r} already")
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
        after a reset is another record)."""
        now = _text(datetime.now(UTC))
        with self.store.connect() as conn:
            row = conn.execute(
                f"SELECT k.created_at {_WITH_PARENT}"
                f" WHERE k.id = ? AND k.revoked_at IS NULL AND {_PARENT_STANDS}",
                (kid, now, self.master),
            ).fetchone()
        return str(row["created_at"]) if row is not None else None

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
        "INSERT INTO access_keys (hash, label, created_at, expires_at, parent_id, master)"
        " VALUES (?,?,?,?,?,?)",
        (digest(code), label, _text(now), expires, parent_id, master),
    )
    row = conn.execute("SELECT * FROM access_keys WHERE id = ?", (cur.lastrowid,)).fetchone()
    return code, _key_of(row)


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
    )

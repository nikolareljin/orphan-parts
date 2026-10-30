"""Access codes as records: issued by a command and shown once, kept only as a hash with a
label and an expiry, revoked by label. The configured ``DEMO_ACCESS_CODE`` stays the master
code beside them; a code of either kind opens the live door."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.inventory.store import Store

PREFIX = "opl_"
LABEL_MAX = 60
State = Literal["current", "expired", "revoked"]


class AccessKeyError(ValueError):
    """A label that is blank, taken or unknown; a day count below one."""


class AccessKey(BaseModel):
    id: int
    label: str = Field(max_length=LABEL_MAX)
    created_at: str
    expires_at: str | None
    revoked_at: str | None

    def state(self, now: datetime | None = None) -> State:
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= _text(now or datetime.now(UTC)):
            return "expired"
        return "current"


def new_code() -> str:
    """A code nobody can guess: the prefix names it as ours, the rest is 24 random bytes."""
    return PREFIX + secrets.token_urlsafe(24)


def digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _text(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


class AccessKeys:
    def __init__(self, store: Store) -> None:
        self.store = store

    def issue(self, label: str, days: int | None = None) -> tuple[str, AccessKey]:
        """A new code for ``label``, shown once; ``days`` from now it stops working, or never
        when not given. Returns the code and its record."""
        label = label.strip()
        if not label:
            raise AccessKeyError("the label is blank")
        if len(label) > LABEL_MAX:
            raise AccessKeyError(f"the label is longer than {LABEL_MAX} characters")
        if days is not None and days < 1:
            raise AccessKeyError("days must be at least 1")
        now = datetime.now(UTC)
        expires = _text(now + timedelta(days=days)) if days is not None else None
        code = new_code()
        with self.store.connect() as conn:
            taken = conn.execute(
                "SELECT 1 FROM access_keys WHERE label = ? AND revoked_at IS NULL"
                " AND (expires_at IS NULL OR expires_at > ?)",
                (label, _text(now)),
            ).fetchone()
            if taken:
                raise AccessKeyError(f"a current code is labeled {label!r}; revoke it first")
            cur = conn.execute(
                "INSERT INTO access_keys (hash, label, created_at, expires_at) VALUES (?,?,?,?)",
                (digest(code), label, _text(now), expires),
            )
            row = conn.execute(
                "SELECT * FROM access_keys WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return code, _key_of(row)

    def all(self) -> list[AccessKey]:
        with self.store.connect() as conn:
            rows = conn.execute("SELECT * FROM access_keys ORDER BY id").fetchall()
        return [_key_of(r) for r in rows]

    def revoke(self, label: str) -> AccessKey:
        """The newest unrevoked code with this label stops working now, with every session it
        opened."""
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
        """The record's issue time when it stands unrevoked, else None (one indexed read; the
        gate asks on every request carrying the record's id, and signs the time into the
        session so that a record with the same id after a reset is another record)."""
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT created_at, revoked_at FROM access_keys WHERE id = ?", (kid,)
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        return str(row["created_at"])

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
        with self.store.connect() as conn:
            rows = conn.execute("SELECT * FROM access_keys WHERE revoked_at IS NULL").fetchall()
        now = datetime.now(UTC)
        out: list[tuple[AccessKey, str]] = []
        for row in rows:
            key = _key_of(row)
            if key.state(now) == "current":
                out.append((key, str(row["hash"])))
        return out


def _key_of(row: object) -> AccessKey:
    r = row  # sqlite3.Row
    return AccessKey(
        id=int(r["id"]),  # type: ignore[index]
        label=str(r["label"]),  # type: ignore[index]
        created_at=str(r["created_at"]),  # type: ignore[index]
        expires_at=r["expires_at"],  # type: ignore[index]
        revoked_at=r["revoked_at"],  # type: ignore[index]
    )

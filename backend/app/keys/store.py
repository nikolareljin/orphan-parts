"""The access codes' own SQLite file under DATA_DIR (KEYS_DB_FILE), apart from the inventory:
a demo reset deletes the inventory file and loads the set again, and the codes handed out,
with what each has used, stay. A file made by this build takes over the records an older
build kept in the inventory, once."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.config import Settings
from app.inventory.store import Store

log = logging.getLogger("app.keys")

# version 1: the records as the inventory kept them (hash, label, dates, what paired a
# phone's), with what a code may do: its scope, whether it is answered from the recordings
# only, and its limits; and what each code used per UTC day, live calls and dollars
_KEYS_V1 = """
CREATE TABLE IF NOT EXISTS access_keys (
    id INTEGER PRIMARY KEY,
    hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    parent_id INTEGER,
    master TEXT,
    scope TEXT NOT NULL DEFAULT 'owner',
    recorded INTEGER NOT NULL DEFAULT 0,
    calls_per_day INTEGER,
    max_usd REAL
);
CREATE TABLE IF NOT EXISTS key_usage (
    key_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    usd REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, day)
);
"""

KEY_MIGRATIONS: dict[int, str] = {1: _KEYS_V1}
_ADOPTED = ("id", "hash", "label", "created_at", "expires_at", "revoked_at", "parent_id", "master")


def keys_store(path: Path, journal_mode: str = "WAL") -> Store:
    """The codes' file at ``path``, made or brought up to date."""
    return Store(path, journal_mode, migrations=KEY_MIGRATIONS)


def open_keys(settings: Settings) -> Store:
    """The codes' file, made on first use; a new one takes over the inventory's records."""
    path = settings.keys_db_path
    fresh = not path.exists()
    store = keys_store(path, settings.sqlite_journal_mode)
    if fresh:
        # the hashes, labels and use are the operator's alone: readable by the service only
        try:
            path.chmod(0o600)
        except OSError as exc:
            log.warning("the codes' file keeps its permissions: %s", exc)
        adopt(store, settings.inventory_db_path)
    return store


def adopt(store: Store, inventory: Path) -> int:
    """The records an older build kept in the inventory's access_keys table, copied with their
    ids (a session names its record by id), as owner codes: what they were. Returns how many."""
    if not inventory.is_file():
        return 0
    src = sqlite3.connect(f"file:{inventory}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        have = {r[1] for r in src.execute("PRAGMA table_info(access_keys)")}
        if not have:
            return 0
        columns = [c for c in _ADOPTED if c in have]
        rows = src.execute(f"SELECT {', '.join(columns)} FROM access_keys ORDER BY id").fetchall()
    except sqlite3.Error as exc:
        log.warning("the inventory's access codes could not be read: %s", exc)
        return 0
    finally:
        src.close()
    with store.connect() as conn:
        for row in rows:
            conn.execute(
                f"INSERT OR IGNORE INTO access_keys ({', '.join(columns)})"
                f" VALUES ({', '.join('?' for _ in columns)})",
                tuple(row[c] for c in columns),
            )
    if rows:
        log.info("access codes moved out of the inventory", extra={"count": len(rows)})
    return len(rows)

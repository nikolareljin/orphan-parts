"""SQLite under DATA_DIR: one file, schema versioned, writes serialised."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    condition TEXT NOT NULL DEFAULT '',
    faults TEXT NOT NULL DEFAULT '',
    tests_done TEXT NOT NULL DEFAULT '',
    accessories TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT 'keep',
    availability TEXT NOT NULL DEFAULT 'available',
    parent_id INTEGER REFERENCES items(id),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE assertions (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    raw TEXT NOT NULL DEFAULT '',
    review TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX assertions_by_item ON assertions (item_id, field);
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    change TEXT NOT NULL,
    version INTEGER NOT NULL
);
CREATE INDEX events_by_item ON events (item_id);
"""


class SchemaTooNewError(RuntimeError):
    pass


class Store:
    """One connection per operation under one lock: one owner, one process, no surprises."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            found = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if found == 0:
                conn.executescript(_SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif found > SCHEMA_VERSION:
                raise SchemaTooNewError(
                    f"{path} has schema version {found}; this build knows {SCHEMA_VERSION}"
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """A connection inside a transaction: committed on success, rolled back on error."""
        with self._lock:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

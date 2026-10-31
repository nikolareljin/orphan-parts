"""SQLite under DATA_DIR: one file, schema versioned, writes serialised."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 12

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

# version 2: the item's category profile, and measurements with the photo they were made on
_SCHEMA_V2 = """
ALTER TABLE items ADD COLUMN profile TEXT NOT NULL DEFAULT '';
CREATE TABLE measurements (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    assertion_id INTEGER REFERENCES assertions(id),
    feature TEXT NOT NULL,
    result TEXT NOT NULL,
    photo BLOB NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX measurements_by_item ON measurements (item_id);
"""

# version 3: listing drafts, each written from one item version, with its checklist state
_SCHEMA_V3 = """
CREATE TABLE drafts (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    mode TEXT NOT NULL,
    version INTEGER NOT NULL,
    item_version INTEGER NOT NULL,
    content TEXT NOT NULL,
    checklist TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX drafts_by_item ON drafts (item_id, mode);
"""

# version 4: price guidance per item version, and sales the owner reports, kept apart
_SCHEMA_V4 = """
CREATE TABLE price_guidance (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    version INTEGER NOT NULL,
    item_version INTEGER NOT NULL,
    content TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX price_guidance_by_item ON price_guidance (item_id);
CREATE TABLE price_reports (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    sold_on TEXT NOT NULL,
    note TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX price_reports_by_item ON price_reports (item_id);
"""

# version 5: missing-item searches run by handoff, and the candidates brought back for them
_SCHEMA_V5 = """
CREATE TABLE searches (
    id INTEGER PRIMARY KEY,
    need_item_id INTEGER REFERENCES items(id),
    profile TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    handoff_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE candidates (
    id INTEGER PRIMARY KEY,
    search_id INTEGER NOT NULL REFERENCES searches(id),
    source_kind TEXT NOT NULL,
    observed_on TEXT NOT NULL,
    state TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    assessed_at TEXT NOT NULL
);
CREATE INDEX candidates_by_search ON candidates (search_id);
"""

# version 6: the owner's preferences, projects proposed from templates, and the items
# allocated to them, exploratory or committed
_SCHEMA_V6 = """
CREATE TABLE preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    template TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE allocations (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    item_id INTEGER NOT NULL REFERENCES items(id),
    requirement TEXT NOT NULL,
    why TEXT NOT NULL,
    committed INTEGER NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX allocations_by_item ON allocations (item_id);
CREATE INDEX allocations_by_project ON allocations (project_id);
"""

# version 7: build packs, one document per writing, with the digest of its inputs
_SCHEMA_V7 = """
CREATE TABLE packs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL,
    digest TEXT NOT NULL,
    markdown TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX packs_by_project ON packs (project_id);
"""

# version 8: captures from the phone, kept until processed and deleted
_SCHEMA_V8 = """
CREATE TABLE captures (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    deleted_at TEXT
);
"""

# version 9: access codes as records: the hash, a label, when it was issued, expires, was revoked
_SCHEMA_V9 = """
CREATE TABLE access_keys (
    id INTEGER PRIMARY KEY,
    hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT
);
"""

_SCHEMA_V10 = """
ALTER TABLE items ADD COLUMN public INTEGER NOT NULL DEFAULT 0;
ALTER TABLE captures ADD COLUMN public INTEGER NOT NULL DEFAULT 0;
"""

# version 11: what an item is good for, one answer per asking, written from one item version
_SCHEMA_V11 = """
CREATE TABLE uses (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    version INTEGER NOT NULL,
    item_version INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX uses_by_item ON uses (item_id);
"""

# version 12: a phone's code names what paired it: the issued record, or a digest of the
# master code it was claimed under, so it ends when that one does
_SCHEMA_V12 = """
ALTER TABLE access_keys ADD COLUMN parent_id INTEGER;
ALTER TABLE access_keys ADD COLUMN master TEXT;
"""

MIGRATIONS: dict[int, str] = {
    1: _SCHEMA,
    2: _SCHEMA_V2,
    3: _SCHEMA_V3,
    4: _SCHEMA_V4,
    5: _SCHEMA_V5,
    6: _SCHEMA_V6,
    7: _SCHEMA_V7,
    8: _SCHEMA_V8,
    9: _SCHEMA_V9,
    10: _SCHEMA_V10,
    11: _SCHEMA_V11,
    12: _SCHEMA_V12,
}


class SchemaTooNewError(RuntimeError):
    pass


class Store:
    """One connection per operation under one lock: one owner, one process, no surprises."""

    def __init__(self, path: Path, journal_mode: str = "WAL") -> None:
        self.path = path
        self.journal_mode = journal_mode
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            found = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if found > SCHEMA_VERSION:
                raise SchemaTooNewError(
                    f"{path} has schema version {found}; this build knows {SCHEMA_VERSION}"
                )
            # each step is one script; a file at version N gets steps N+1 onwards
            for version in range(found + 1, SCHEMA_VERSION + 1):
                conn.executescript(MIGRATIONS[version])
                conn.execute(f"PRAGMA user_version = {version}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """A connection inside a transaction: committed on success, rolled back on error."""
        with self._lock:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA journal_mode = {self.journal_mode}")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

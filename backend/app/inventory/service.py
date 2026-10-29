"""Inventory operations. Every write bumps the item version and records an event."""

import sqlite3
from datetime import UTC, datetime

from app.config import Settings
from app.inventory.schema import (
    Assertion,
    ComponentCreate,
    Event,
    FieldCreate,
    Item,
    ItemCreate,
    ItemPatch,
    ItemSummary,
    Review,
)
from app.inventory.store import Store

OWNER = "owner"
EDITABLE = (
    "name",
    "item_type",
    "condition",
    "faults",
    "tests_done",
    "accessories",
    "location",
    "notes",
    "intent",
    "availability",
)


class NotFoundError(LookupError):
    pass


class VersionConflictError(ValueError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def current_fields(assertions: list[Assertion]) -> dict[str, Assertion]:
    """Per field: the latest accepted value, else the latest proposed one. Rejected never shows."""
    out: dict[str, Assertion] = {}
    for a in assertions:
        if a.review == "rejected":
            continue
        cur = out.get(a.field)
        if cur is None or a.review == "accepted" or cur.review != "accepted":
            out[a.field] = a
    return out


class Inventory:
    def __init__(self, settings: Settings) -> None:
        self.store = Store(settings.inventory_db_path)

    # creation

    def create(self, spec: ItemCreate) -> Item:
        ex = spec.extraction
        item_type = spec.item_type.strip() or (ex.item_type if ex else "") or "item"
        name = spec.name.strip() or item_type
        at = now()
        with self.store.connect() as conn:
            if spec.parent_id is not None:
                self._row(conn, spec.parent_id)
            item_id = self._insert_item(conn, spec, name=name, item_type=item_type, at=at)
            count = 0
            if ex is not None:
                for field, ev in ex.fields.items():
                    conn.execute(
                        "INSERT INTO assertions (item_id, field, value, unit, provenance,"
                        " confidence, source, raw, review, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            item_id,
                            field,
                            ev.value,
                            ev.unit,
                            "observed",
                            ev.confidence,
                            ev.source,
                            ev.raw,
                            "proposed",
                            at,
                        ),
                    )
                    count += 1
            change = (
                f"created from a label reading with {count} observed field(s)"
                if ex is not None
                else "created"
            )
            self._event(conn, item_id, change, 1, at)
            return self._item(conn, item_id)

    def add_component(self, item_id: int, spec: ComponentCreate) -> Item:
        """A part separated from the whole: its own record, and the parent says it is gone."""
        at = now()
        with self.store.connect() as conn:
            parent = self._row(conn, item_id)
            child_spec = ItemCreate(
                name=spec.name,
                item_type=spec.item_type or spec.name,
                condition=spec.condition,
                notes=spec.notes,
                parent_id=item_id,
                intent=parent["intent"],
            )
            child_id = self._insert_item(
                conn, child_spec, name=spec.name.strip(), item_type=child_spec.item_type, at=at
            )
            self._event(conn, child_id, f"separated from item {item_id}", 1, at)
            line = f"{spec.name.strip()} separated into item {child_id}"
            faults = f"{parent['faults']}\n{line}".strip()
            version = int(parent["version"]) + 1
            conn.execute(
                "UPDATE items SET faults = ?, version = ?, updated_at = ? WHERE id = ?",
                (faults, version, at, item_id),
            )
            self._event(conn, item_id, f"component separated: {spec.name.strip()}", version, at)
            return self._item(conn, child_id)

    # reading

    def list_items(self) -> list[ItemSummary]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT i.*, (SELECT COUNT(DISTINCT a.field) FROM assertions a"
                " WHERE a.item_id = i.id AND a.review != 'rejected') AS field_count"
                " FROM items i WHERE i.deleted_at IS NULL ORDER BY i.id DESC"
            ).fetchall()
            return [self._summary(r) for r in rows]

    def get(self, item_id: int) -> Item:
        with self.store.connect() as conn:
            return self._item(conn, item_id)

    def events(self, item_id: int) -> list[Event]:
        with self.store.connect() as conn:
            self._row(conn, item_id, include_deleted=True)
            rows = conn.execute(
                "SELECT * FROM events WHERE item_id = ? ORDER BY id", (item_id,)
            ).fetchall()
            return [Event(**dict(r)) for r in rows]

    # changes

    def update(self, item_id: int, patch: ItemPatch) -> Item:
        data = patch.model_dump(exclude_unset=True, exclude={"version"})
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            if patch.version is not None and patch.version != int(row["version"]):
                raise VersionConflictError(
                    f"item {item_id} is at version {row['version']}, not {patch.version}"
                )
            changed = [k for k in EDITABLE if k in data and data[k] != row[k]]
            if not changed:
                return self._item(conn, item_id)
            version = int(row["version"]) + 1
            assignments = ", ".join(f"{k} = ?" for k in changed)
            # column names come from EDITABLE, never from the request
            conn.execute(
                f"UPDATE items SET {assignments}, version = ?, updated_at = ? WHERE id = ?",
                (*[data[k] for k in changed], version, at, item_id),
            )
            self._event(conn, item_id, "changed " + ", ".join(changed), version, at)
            return self._item(conn, item_id)

    def add_field(self, item_id: int, spec: FieldCreate) -> Item:
        """The owner's value for a field, accepted as stated, beside whatever was observed."""
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            conn.execute(
                "INSERT INTO assertions (item_id, field, value, unit, provenance, confidence,"
                " source, raw, review, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    spec.field,
                    spec.value.strip(),
                    spec.unit.strip(),
                    spec.provenance,
                    1.0,
                    "user_edit",
                    spec.raw,
                    "accepted",
                    at,
                ),
            )
            version = self._bump(conn, row, at)
            shown = f"{spec.value.strip()} {spec.unit.strip()}".strip()
            change = f"{spec.field} set to {shown} ({spec.provenance})"
            self._event(conn, item_id, change, version, at)
            return self._item(conn, item_id)

    def review(self, item_id: int, assertion_id: int, review: Review) -> Item:
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            found = conn.execute(
                "SELECT field, review FROM assertions WHERE id = ? AND item_id = ?",
                (assertion_id, item_id),
            ).fetchone()
            if found is None:
                raise NotFoundError(f"item {item_id} has no assertion {assertion_id}")
            if found["review"] == review:
                return self._item(conn, item_id)
            conn.execute("UPDATE assertions SET review = ? WHERE id = ?", (review, assertion_id))
            version = self._bump(conn, row, at)
            self._event(conn, item_id, f"{found['field']} {review}", version, at)
            return self._item(conn, item_id)

    def delete(self, item_id: int) -> None:
        """Hidden, not erased: the record and its events stay for the audit trail."""
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            version = int(row["version"]) + 1
            conn.execute(
                "UPDATE items SET deleted_at = ?, version = ?, updated_at = ? WHERE id = ?",
                (at, version, at, item_id),
            )
            self._event(conn, item_id, "deleted", version, at)

    # internals

    def _insert_item(
        self, conn: sqlite3.Connection, spec: ItemCreate, *, name: str, item_type: str, at: str
    ) -> int:
        cur = conn.execute(
            "INSERT INTO items (name, item_type, condition, faults, tests_done, accessories,"
            " location, notes, intent, availability, parent_id, version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                name,
                item_type,
                spec.condition,
                spec.faults,
                spec.tests_done,
                spec.accessories,
                spec.location,
                spec.notes,
                spec.intent,
                spec.availability,
                spec.parent_id,
                at,
                at,
            ),
        )
        return int(cur.lastrowid or 0)

    def _row(
        self, conn: sqlite3.Connection, item_id: int, *, include_deleted: bool = False
    ) -> sqlite3.Row:
        row: sqlite3.Row | None = conn.execute(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None or (row["deleted_at"] is not None and not include_deleted):
            raise NotFoundError(f"no item {item_id}")
        return row

    def _bump(self, conn: sqlite3.Connection, row: sqlite3.Row, at: str) -> int:
        version = int(row["version"]) + 1
        conn.execute(
            "UPDATE items SET version = ?, updated_at = ? WHERE id = ?", (version, at, row["id"])
        )
        return version

    def _event(
        self, conn: sqlite3.Connection, item_id: int, change: str, version: int, at: str
    ) -> None:
        conn.execute(
            "INSERT INTO events (item_id, at, actor, change, version) VALUES (?,?,?,?,?)",
            (item_id, at, OWNER, change, version),
        )

    def _summary(self, row: sqlite3.Row) -> ItemSummary:
        return ItemSummary(
            id=row["id"],
            name=row["name"],
            item_type=row["item_type"],
            condition=row["condition"],
            intent=row["intent"],
            availability=row["availability"],
            parent_id=row["parent_id"],
            field_count=row["field_count"],
            version=row["version"],
            updated_at=row["updated_at"],
        )

    def _item(self, conn: sqlite3.Connection, item_id: int) -> Item:
        row = self._row(conn, item_id)
        assertions = [
            Assertion(**dict(r))
            for r in conn.execute(
                "SELECT * FROM assertions WHERE item_id = ? ORDER BY id", (item_id,)
            ).fetchall()
        ]
        fields = current_fields(assertions)
        components = [
            int(r["id"])
            for r in conn.execute(
                "SELECT id FROM items WHERE parent_id = ? AND deleted_at IS NULL ORDER BY id",
                (item_id,),
            ).fetchall()
        ]
        return Item(
            id=row["id"],
            name=row["name"],
            item_type=row["item_type"],
            condition=row["condition"],
            faults=row["faults"],
            tests_done=row["tests_done"],
            accessories=row["accessories"],
            location=row["location"],
            notes=row["notes"],
            intent=row["intent"],
            availability=row["availability"],
            parent_id=row["parent_id"],
            field_count=len(fields),
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            fields=fields,
            assertions=assertions,
            components=components,
        )

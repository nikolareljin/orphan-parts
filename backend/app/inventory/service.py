"""Inventory operations. Every write bumps the item version and records an event."""

import json
import sqlite3
from datetime import UTC, datetime

from app.config import Settings
from app.extract.schema import Source
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
from app.measure.schema import Measurement, MeasureResult

OWNER = "owner"
EDITABLE = (
    "name",
    "item_type",
    "profile",
    "condition",
    "faults",
    "tests_done",
    "accessories",
    "location",
    "notes",
    "intent",
    "availability",
)
# One fixed statement per editable column: nothing from a request ever shapes the SQL.
_SET_ONE = "UPDATE items SET <column> = ?, version = ?, updated_at = ? WHERE id = ?"
SET_COLUMN = {k: _SET_ONE.replace("<column>", k) for k in EDITABLE}


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
        self.store = Store(settings.inventory_db_path, settings.sqlite_journal_mode)

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

    def list_items(self, *, public_only: bool = False) -> list[ItemSummary]:
        """Every item that is not deleted; for the demo visitor, only the public ones."""
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT i.*, (SELECT COUNT(DISTINCT a.field) FROM assertions a"
                " WHERE a.item_id = i.id AND a.review != 'rejected') AS field_count"
                " FROM items i WHERE i.deleted_at IS NULL AND (? = 0 OR i.public = 1)"
                " ORDER BY i.id DESC",
                (int(public_only),),
            ).fetchall()
            return [self._summary(r) for r in rows]

    def get(self, item_id: int, *, public_only: bool = False) -> Item:
        """The item; a private one is not there at all for the demo visitor."""
        with self.store.connect() as conn:
            item = self._item(conn, item_id)
            if public_only and not item.public:
                raise NotFoundError(f"no item {item_id}")
            return item

    def set_public(self, item_id: int, public: bool) -> Item:
        """Shown to the demo visitor, or not: the owner's choice, item by item."""
        with self.store.connect() as conn:
            self._row(conn, item_id)
            conn.execute("UPDATE items SET public = ? WHERE id = ?", (int(public), item_id))
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
        # a key sent as null means "not given", never "set to nothing"
        data = {
            k: v
            for k, v in patch.model_dump(exclude_unset=True, exclude={"version"}).items()
            if v is not None
        }
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
            for k in changed:
                conn.execute(SET_COLUMN[k], (data[k], version, at, item_id))
            self._event(conn, item_id, "changed " + ", ".join(changed), version, at)
            return self._item(conn, item_id)

    def add_field(self, item_id: int, spec: FieldCreate, *, source: Source = "user_edit") -> Item:
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
                    source,
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

    def add_measurement(self, item_id: int, result: MeasureResult, photo: bytes) -> Measurement:
        """Store the capture with its result. An accepted one proposes an observed value on the
        item; a refused one is kept too, so the unusable-capture rate is on record."""
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            assertion_id: int | None = None
            if (
                result.accepted
                and result.value_mm is not None
                and result.uncertainty_mm is not None
            ):
                raw = (
                    f"{result.value_mm:.1f} ± {result.uncertainty_mm:.2f} mm"
                    f" ({result.method.replace('_', ' ')})"
                )
                cur = conn.execute(
                    "INSERT INTO assertions (item_id, field, value, unit, provenance, confidence,"
                    " source, raw, review, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        item_id,
                        result.feature,
                        f"{result.value_mm:.1f}",
                        "mm",
                        "observed",
                        1.0,
                        "measurement",
                        raw,
                        "proposed",
                        at,
                    ),
                )
                assertion_id = int(cur.lastrowid or 0)
                change = f"{result.feature} measured: {raw}"
            else:
                change = f"{result.feature} capture refused: {result.redo}"
            cur = conn.execute(
                "INSERT INTO measurements (item_id, assertion_id, feature, result, photo, at)"
                " VALUES (?,?,?,?,?,?)",
                (item_id, assertion_id, result.feature, result.model_dump_json(), photo, at),
            )
            measurement_id = int(cur.lastrowid or 0)
            version = self._bump(conn, row, at)
            self._event(conn, item_id, change, version, at)
            return self._measurement(conn, item_id, measurement_id)

    def measurements(self, item_id: int) -> list[Measurement]:
        with self.store.connect() as conn:
            self._row(conn, item_id)
            ids = [
                int(r["id"])
                for r in conn.execute(
                    "SELECT id FROM measurements WHERE item_id = ? ORDER BY id", (item_id,)
                ).fetchall()
            ]
            return [self._measurement(conn, item_id, mid) for mid in ids]

    def measurement_photo(self, item_id: int, measurement_id: int) -> bytes:
        with self.store.connect() as conn:
            self._row(conn, item_id)
            found = conn.execute(
                "SELECT photo FROM measurements WHERE id = ? AND item_id = ?",
                (measurement_id, item_id),
            ).fetchone()
            if found is None:
                raise NotFoundError(f"item {item_id} has no measurement {measurement_id}")
            return bytes(found["photo"])

    # listing drafts: stored as written, read back with the item's current version beside them

    _DRAFT_SELECT = (
        "SELECT d.*, i.version AS current_item_version FROM drafts d"
        " JOIN items i ON i.id = d.item_id"
    )

    def add_draft(self, item_id: int, mode: str, content: str, checklist: str) -> sqlite3.Row:
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            last = conn.execute(
                "SELECT MAX(version) FROM drafts WHERE item_id = ? AND mode = ?", (item_id, mode)
            ).fetchone()[0]
            version = int(last or 0) + 1
            # written from this item version; writing a draft changes nothing about the item,
            # so the version stays and another draft does not make this one stale
            item_version = int(row["version"])
            self._event(conn, item_id, f"{mode} draft written (v{version})", item_version, at)
            cur = conn.execute(
                "INSERT INTO drafts (item_id, mode, version, item_version, content, checklist, at)"
                " VALUES (?,?,?,?,?,?,?)",
                (item_id, mode, version, item_version, content, checklist, at),
            )
            return self._draft(conn, int(cur.lastrowid or 0))

    def drafts(self, item_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            self._row(conn, item_id)
            return conn.execute(
                self._DRAFT_SELECT + " WHERE d.item_id = ? ORDER BY d.id", (item_id,)
            ).fetchall()

    def draft(self, draft_id: int) -> sqlite3.Row:
        with self.store.connect() as conn:
            return self._draft(conn, draft_id)

    def set_checklist(self, draft_id: int, checklist: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            self._draft(conn, draft_id)
            conn.execute("UPDATE drafts SET checklist = ? WHERE id = ?", (checklist, draft_id))
            return self._draft(conn, draft_id)

    def _draft(self, conn: sqlite3.Connection, draft_id: int) -> sqlite3.Row:
        # a hidden item's drafts are hidden with it
        row: sqlite3.Row | None = conn.execute(
            self._DRAFT_SELECT + " WHERE d.id = ? AND i.deleted_at IS NULL", (draft_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no draft {draft_id}")
        return row

    # price guidance: stored as written, read back with the item's current version beside it

    _GUIDANCE_SELECT = (
        "SELECT g.*, i.version AS current_item_version FROM price_guidance g"
        " JOIN items i ON i.id = g.item_id"
    )

    def add_guidance(self, item_id: int, content: str) -> sqlite3.Row:
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            last = conn.execute(
                "SELECT MAX(version) FROM price_guidance WHERE item_id = ?", (item_id,)
            ).fetchone()[0]
            version = int(last or 0) + 1
            # written from this item version; asking what it is worth changes nothing about it
            item_version = int(row["version"])
            self._event(conn, item_id, f"price guidance written (v{version})", item_version, at)
            cur = conn.execute(
                "INSERT INTO price_guidance (item_id, version, item_version, content, at)"
                " VALUES (?,?,?,?,?)",
                (item_id, version, item_version, content, at),
            )
            return self._guidance(conn, int(cur.lastrowid or 0))

    def guidances(self, item_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            self._row(conn, item_id)
            return conn.execute(
                self._GUIDANCE_SELECT + " WHERE g.item_id = ? ORDER BY g.id", (item_id,)
            ).fetchall()

    def _guidance(self, conn: sqlite3.Connection, guidance_id: int) -> sqlite3.Row:
        row: sqlite3.Row | None = conn.execute(
            self._GUIDANCE_SELECT + " WHERE g.id = ? AND i.deleted_at IS NULL", (guidance_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no price guidance {guidance_id}")
        return row

    def add_price_report(
        self, item_id: int, *, price: float, currency: str, sold_on: str, note: str
    ) -> sqlite3.Row:
        """A sale the owner knows of. An event on the item; the item itself is unchanged."""
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            cur = conn.execute(
                "INSERT INTO price_reports (item_id, price, currency, sold_on, note, at)"
                " VALUES (?,?,?,?,?,?)",
                (item_id, price, currency, sold_on, note.strip(), at),
            )
            self._event(
                conn,
                item_id,
                f"sale reported: {price:g} {currency} on {sold_on}",
                int(row["version"]),
                at,
            )
            found: sqlite3.Row = conn.execute(
                "SELECT * FROM price_reports WHERE id = ?", (int(cur.lastrowid or 0),)
            ).fetchone()
            return found

    def price_reports(self, item_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            self._row(conn, item_id)
            return conn.execute(
                "SELECT * FROM price_reports WHERE item_id = ? ORDER BY sold_on, id", (item_id,)
            ).fetchall()

    # what the item is good for: stored as written, read back with the item's current version

    _USES_SELECT = (
        "SELECT u.*, i.version AS current_item_version FROM uses u JOIN items i ON i.id = u.item_id"
    )

    def add_uses(self, item_id: int, content: str, *, item_version: int) -> sqlite3.Row:
        at = now()
        with self.store.connect() as conn:
            self._row(conn, item_id)
            last = conn.execute(
                "SELECT MAX(version) FROM uses WHERE item_id = ?", (item_id,)
            ).fetchone()[0]
            version = int(last or 0) + 1
            # Keep the version used in the brief, even if the item changed during the request.
            self._event(conn, item_id, f"uses written (v{version})", item_version, at)
            cur = conn.execute(
                "INSERT INTO uses (item_id, version, item_version, content, created_at)"
                " VALUES (?,?,?,?,?)",
                (item_id, version, item_version, content, at),
            )
            found: sqlite3.Row | None = conn.execute(
                self._USES_SELECT + " WHERE u.id = ?", (int(cur.lastrowid or 0),)
            ).fetchone()
            assert found is not None
            return found

    def uses(self, item_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            self._row(conn, item_id)
            return conn.execute(
                self._USES_SELECT + " WHERE u.item_id = ? ORDER BY u.id", (item_id,)
            ).fetchall()

    def decide(
        self, item_id: int, intent: str, change: str, *, said: bool, version: int | None = None
    ) -> Item:
        """The owner's decision: the intent it implies is set and the decision itself is the
        event line, so the history keeps the why. The version is bumped only when the item
        changes: a new intent, or a note (``said``) that gives the item a new why. The same
        choice again, with nothing said, is an event and nothing more; the guidance and the
        uses written before it stay current. With ``version`` set, a choice made from an older
        version of the item is refused and nothing is written."""
        at = now()
        with self.store.connect() as conn:
            row = self._row(conn, item_id)
            if version is not None and version != int(row["version"]):
                raise VersionConflictError(
                    f"item {item_id} is at version {row['version']}, not {version}"
                )
            version = int(row["version"])
            if intent != str(row["intent"]) or said:
                version += 1
                conn.execute(SET_COLUMN["intent"], (intent, version, at, item_id))
            self._event(conn, item_id, change, version, at)
            return self._item(conn, item_id)

    # missing-item searches and their candidates; a search may name the item it is for

    # the search as shown (head, without the listings brought back) and how many listings it
    # holds, counted by SQLite rather than by parsing them
    _SEARCH_SELECT = (
        "SELECT s.*, (SELECT COUNT(*) FROM candidates c WHERE c.search_id = s.id)"
        " AS candidate_count, json_remove(s.content, '$.listings') AS head,"
        " COALESCE(json_array_length(s.content, '$.listings'), 0) AS listing_count"
        " FROM searches s"
    )

    def add_search(
        self, *, need_item_id: int | None, profile: str, title: str, content: str, handoff_url: str
    ) -> sqlite3.Row:
        at = now()
        with self.store.connect() as conn:
            if need_item_id is not None:
                row = self._row(conn, need_item_id)
                self._event(conn, need_item_id, f"search opened: {title}", int(row["version"]), at)
            cur = conn.execute(
                "INSERT INTO searches (need_item_id, profile, title, content, status, handoff_url,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (need_item_id, profile, title, content, "open", handoff_url, at, at),
            )
            return self._search(conn, int(cur.lastrowid or 0))

    def searches(self) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            return conn.execute(self._SEARCH_SELECT + " ORDER BY s.id DESC").fetchall()

    def search(self, search_id: int) -> sqlite3.Row:
        with self.store.connect() as conn:
            return self._search(conn, search_id)

    def update_search(self, search_id: int, status: str, content: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            self._search(conn, search_id)
            conn.execute(
                "UPDATE searches SET status = ?, content = ?, updated_at = ? WHERE id = ?",
                (status, content, now(), search_id),
            )
            return self._search(conn, search_id)

    def _search(self, conn: sqlite3.Connection, search_id: int) -> sqlite3.Row:
        row: sqlite3.Row | None = conn.execute(
            self._SEARCH_SELECT + " WHERE s.id = ?", (search_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no search {search_id}")
        return row

    def add_candidate(
        self, search_id: int, source_kind: str, observed_on: str, state: str, content: str
    ) -> sqlite3.Row:
        at = now()
        with self.store.connect() as conn:
            self._search(conn, search_id)
            cur = conn.execute(
                "INSERT INTO candidates (search_id, source_kind, observed_on, state, content,"
                " created_at, assessed_at) VALUES (?,?,?,?,?,?,?)",
                (search_id, source_kind, observed_on, state, content, at, at),
            )
            conn.execute("UPDATE searches SET updated_at = ? WHERE id = ?", (at, search_id))
            return self._candidate(conn, int(cur.lastrowid or 0))

    def candidates(self, search_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            self._search(conn, search_id)
            return conn.execute(
                "SELECT * FROM candidates WHERE search_id = ? ORDER BY id", (search_id,)
            ).fetchall()

    def candidate(self, candidate_id: int) -> sqlite3.Row:
        with self.store.connect() as conn:
            return self._candidate(conn, candidate_id)

    def update_candidate(self, candidate_id: int, state: str, content: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            self._candidate(conn, candidate_id)
            conn.execute(
                "UPDATE candidates SET state = ?, content = ?, assessed_at = ? WHERE id = ?",
                (state, content, now(), candidate_id),
            )
            return self._candidate(conn, candidate_id)

    def _candidate(self, conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row:
        row: sqlite3.Row | None = conn.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no candidate {candidate_id}")
        return row

    # preferences, projects and allocations

    def preferences(self) -> sqlite3.Row | None:
        with self.store.connect() as conn:
            row: sqlite3.Row | None = conn.execute(
                "SELECT * FROM preferences WHERE id = 1"
            ).fetchone()
            return row

    def set_preferences(self, content: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO preferences (id, content, updated_at) VALUES (1, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET content = excluded.content,"
                " updated_at = excluded.updated_at",
                (content, now()),
            )
            found: sqlite3.Row = conn.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
            return found

    def add_project(
        self, template: str, title: str, content: str, allocations: list[tuple[int, str, str]]
    ) -> sqlite3.Row:
        at = now()
        with self.store.connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (template, title, status, version, content, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?)",
                (template, title, "proposed", 1, content, at, at),
            )
            project_id = int(cur.lastrowid or 0)
            for item_id, requirement, why in allocations:
                row = self._row(conn, item_id)
                conn.execute(
                    "INSERT INTO allocations (project_id, item_id, requirement, why, committed, at)"
                    " VALUES (?,?,?,?,0,?)",
                    (project_id, item_id, requirement, why, at),
                )
                self._event(conn, item_id, f"proposed for: {title}", int(row["version"]), at)
            return self._project(conn, project_id)

    def projects(self) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            return conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()

    def project(self, project_id: int) -> sqlite3.Row:
        with self.store.connect() as conn:
            return self._project(conn, project_id)

    def update_project(self, project_id: int, status: str, content: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            row = self._project(conn, project_id)
            conn.execute(
                "UPDATE projects SET status = ?, content = ?, version = ?, updated_at = ?"
                " WHERE id = ?",
                (status, content, int(row["version"]) + 1, now(), project_id),
            )
            return self._project(conn, project_id)

    def allocations(self, project_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT a.*, i.name AS item_name FROM allocations a"
                " JOIN items i ON i.id = a.item_id AND i.deleted_at IS NULL"
                " WHERE a.project_id = ? ORDER BY a.id",
                (project_id,),
            ).fetchall()

    def set_committed(self, project_id: int, committed: bool) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "UPDATE allocations SET committed = ? WHERE project_id = ?",
                (1 if committed else 0, project_id),
            )

    def committed_elsewhere(self, item_id: int, project_id: int) -> list[sqlite3.Row]:
        """The other projects an item is committed to: selected, being built or done; a deleted
        item holds nothing."""
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT a.project_id, p.title FROM allocations a"
                " JOIN projects p ON p.id = a.project_id"
                " JOIN items i ON i.id = a.item_id AND i.deleted_at IS NULL"
                " WHERE a.item_id = ? AND a.committed = 1 AND a.project_id != ?"
                " AND p.status IN ('selected', 'building', 'done')",
                (item_id, project_id),
            ).fetchall()

    def add_allocation(
        self, project_id: int, item_id: int, requirement: str, why: str, committed: bool
    ) -> None:
        at = now()
        with self.store.connect() as conn:
            project = self._project(conn, project_id)
            row = self._row(conn, item_id)
            conn.execute(
                "INSERT INTO allocations (project_id, item_id, requirement, why, committed, at)"
                " VALUES (?,?,?,?,?,?)",
                (project_id, item_id, requirement, why, 1 if committed else 0, at),
            )
            self._event(conn, item_id, f"put on: {project['title']}", int(row["version"]), at)

    def release_allocation(self, project_id: int, item_id: int) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "DELETE FROM allocations WHERE project_id = ? AND item_id = ?",
                (project_id, item_id),
            )

    def add_pack(self, project_id: int, digest: str, markdown: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            self._project(conn, project_id)
            last = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM packs WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
            cur = conn.execute(
                "INSERT INTO packs (project_id, version, digest, markdown, created_at)"
                " VALUES (?,?,?,?,?)",
                (project_id, int(last) + 1, digest, markdown, now()),
            )
            found: sqlite3.Row = conn.execute(
                "SELECT * FROM packs WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return found

    def packs(self, project_id: int) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT * FROM packs WHERE project_id = ? ORDER BY version", (project_id,)
            ).fetchall()

    def pack(self, pack_id: int) -> sqlite3.Row:
        with self.store.connect() as conn:
            row: sqlite3.Row | None = conn.execute(
                "SELECT * FROM packs WHERE id = ?", (pack_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"no pack {pack_id}")
            return row

    def _project(self, conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
        row: sqlite3.Row | None = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no project {project_id}")
        return row

    # captures from the phone

    def add_capture(self, content: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            cur = conn.execute(
                "INSERT INTO captures (status, content, created_at) VALUES (?,?,?)",
                ("received", content, now()),
            )
            return self._capture(conn, int(cur.lastrowid or 0))

    def captures(self, *, public_only: bool = False) -> list[sqlite3.Row]:
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT * FROM captures WHERE deleted_at IS NULL AND (? = 0 OR public = 1)"
                " ORDER BY id DESC",
                (int(public_only),),
            ).fetchall()

    def capture(self, capture_id: int, *, public_only: bool = False) -> sqlite3.Row:
        with self.store.connect() as conn:
            row = self._capture(conn, capture_id)
            if public_only and not row["public"]:
                raise NotFoundError(f"no capture {capture_id}")
            return row

    def set_capture_public(self, capture_id: int, public: bool) -> sqlite3.Row:
        with self.store.connect() as conn:
            self._capture(conn, capture_id)
            conn.execute("UPDATE captures SET public = ? WHERE id = ?", (int(public), capture_id))
            return self._capture(conn, capture_id)

    def update_capture(self, capture_id: int, status: str, content: str) -> sqlite3.Row:
        with self.store.connect() as conn:
            self._capture(conn, capture_id)
            conn.execute(
                "UPDATE captures SET status = ?, content = ?, processed_at = ? WHERE id = ?",
                (status, content, now() if status == "processed" else None, capture_id),
            )
            return self._capture(conn, capture_id)

    def delete_capture(self, capture_id: int) -> None:
        with self.store.connect() as conn:
            self._capture(conn, capture_id)
            conn.execute("UPDATE captures SET deleted_at = ? WHERE id = ?", (now(), capture_id))

    def _capture(self, conn: sqlite3.Connection, capture_id: int) -> sqlite3.Row:
        row: sqlite3.Row | None = conn.execute(
            "SELECT * FROM captures WHERE id = ? AND deleted_at IS NULL", (capture_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no capture {capture_id}")
        return row

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
            "INSERT INTO items (name, item_type, profile, condition, faults, tests_done,"
            " accessories, location, notes, intent, availability, parent_id, version,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                name,
                item_type,
                spec.profile,
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

    def _measurement(
        self, conn: sqlite3.Connection, item_id: int, measurement_id: int
    ) -> Measurement:
        found = conn.execute(
            "SELECT id, item_id, assertion_id, result, at FROM measurements"
            " WHERE id = ? AND item_id = ?",
            (measurement_id, item_id),
        ).fetchone()
        if found is None:
            raise NotFoundError(f"item {item_id} has no measurement {measurement_id}")
        return Measurement(
            **json.loads(found["result"]),
            id=found["id"],
            item_id=found["item_id"],
            assertion_id=found["assertion_id"],
            at=found["at"],
        )

    def _summary(self, row: sqlite3.Row) -> ItemSummary:
        return ItemSummary(
            id=row["id"],
            name=row["name"],
            item_type=row["item_type"],
            profile=row["profile"],
            condition=row["condition"],
            intent=row["intent"],
            availability=row["availability"],
            parent_id=row["parent_id"],
            field_count=row["field_count"],
            version=row["version"],
            updated_at=row["updated_at"],
            public=bool(row["public"]),
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
            profile=row["profile"],
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
            public=bool(row["public"]),
        )

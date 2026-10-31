import sqlite3

import pytest

from app.config import Settings
from app.extract.schema import Evidence, Extraction
from app.inventory import (
    Assertion,
    ComponentCreate,
    FieldCreate,
    Inventory,
    ItemCreate,
    ItemPatch,
    NotFoundError,
    VersionConflictError,
    current_fields,
)
from app.inventory.store import MIGRATIONS, SCHEMA_VERSION, SchemaTooNewError, Store


def reading(**fields: tuple[str, str, float]) -> Extraction:
    return Extraction(
        item_type="laptop power adapter",
        label_text="OUTPUT: 19.5V 3.33A",
        fields={
            name: Evidence(value=v, unit=u, confidence=c, source="photo", raw=f"{v}{u}")
            for name, (v, u, c) in fields.items()
        },
        warnings=[],
        photos=1,
        crops=0,
        model="muse-spark-1.3",
        from_fixture=True,
        cost_usd=0.0,
    )


@pytest.fixture
def inventory(settings: Settings) -> Inventory:
    return Inventory(settings)


def test_item_from_a_reading_keeps_every_field_as_a_proposed_observation(
    inventory: Inventory,
) -> None:
    item = inventory.create(
        ItemCreate(
            extraction=reading(output_voltage=("19.5", "V", 0.97), brand=("Orbital", "", 0.9))
        )
    )
    assert item.id == 1
    assert item.name == "laptop power adapter"
    assert item.item_type == "laptop power adapter"
    assert item.intent == "keep"
    assert item.availability == "available"
    assert item.version == 1
    assert set(item.fields) == {"output_voltage", "brand"}
    volts = item.fields["output_voltage"]
    assert (volts.value, volts.unit, volts.confidence) == ("19.5", "V", 0.97)
    assert volts.provenance == "observed"
    assert volts.source == "photo"
    assert volts.review == "proposed"
    assert volts.raw == "19.5V"
    events = inventory.events(item.id)
    assert [e.change for e in events] == ["created from a label reading with 2 observed field(s)"]
    assert events[0].actor == "owner"


def test_item_by_hand_needs_only_a_type(inventory: Inventory) -> None:
    item = inventory.create(ItemCreate(item_type="USB webcam", condition="works"))
    assert item.name == "USB webcam"
    assert item.fields == {}
    assert [e.change for e in inventory.events(item.id)] == ["created"]
    blank = inventory.create(ItemCreate())
    assert blank.name == "item"


def test_list_is_newest_first_with_field_counts_and_no_location(inventory: Inventory) -> None:
    inventory.create(ItemCreate(item_type="first", location="garage shelf B"))
    second = inventory.create(ItemCreate(extraction=reading(brand=("Orbital", "", 0.9))))
    listed = inventory.list_items()
    assert [s.id for s in listed] == [second.id, 1]
    assert listed[0].field_count == 1
    assert listed[1].field_count == 0
    assert "location" not in listed[1].model_dump()


def test_owner_value_sits_beside_the_observation(inventory: Inventory) -> None:
    item = inventory.create(ItemCreate(extraction=reading(output_voltage=("19.5", "V", 0.97))))
    item = inventory.add_field(
        item.id, FieldCreate(field="output_voltage", value="19", unit="V", provenance="tested")
    )
    assert len(item.assertions) == 2
    current = item.fields["output_voltage"]
    assert (current.value, current.provenance, current.review) == ("19", "tested", "accepted")
    assert current.source == "user_edit"
    assert current.confidence == 1.0
    observed = item.assertions[0]
    assert (observed.value, observed.review) == ("19.5", "proposed")
    assert item.version == 2
    assert inventory.events(item.id)[-1].change == "output_voltage set to 19 V (tested)"


def test_accepting_and_rejecting_an_observation(inventory: Inventory) -> None:
    item = inventory.create(
        ItemCreate(
            extraction=reading(output_voltage=("19.5", "V", 0.97), brand=("Orbital", "", 0.4))
        )
    )
    volts = item.fields["output_voltage"]
    brand = item.fields["brand"]
    item = inventory.review(item.id, volts.id, "accepted")
    assert item.fields["output_voltage"].review == "accepted"
    item = inventory.review(item.id, brand.id, "rejected")
    assert "brand" not in item.fields
    assert len(item.assertions) == 2
    assert item.field_count == 1
    assert item.version == 3
    same = inventory.review(item.id, volts.id, "accepted")
    assert same.version == 3
    with pytest.raises(NotFoundError):
        inventory.review(item.id, 999, "accepted")


def test_current_fields_prefers_accepted_then_latest_proposed() -> None:
    def a(i: int, value: str, review: str) -> Assertion:
        return Assertion(
            id=i,
            field="brand",
            value=value,
            provenance="observed",
            confidence=0.5,
            source="photo",
            review=review,  # type: ignore[arg-type]
            at="2026-10-28T00:00:00+00:00",
        )

    assert (
        current_fields([a(1, "one", "proposed"), a(2, "two", "proposed")])["brand"].value == "two"
    )
    accepted_then_proposed = [a(1, "one", "accepted"), a(2, "two", "proposed")]
    assert current_fields(accepted_then_proposed)["brand"].value == "one"
    assert current_fields([a(1, "one", "rejected")]) == {}


def test_update_changes_only_what_differs_and_checks_the_version(inventory: Inventory) -> None:
    item = inventory.create(ItemCreate(item_type="phone", condition="screen cracked"))
    unchanged = inventory.update(item.id, ItemPatch(condition="screen cracked"))
    assert unchanged.version == 1
    changed = inventory.update(item.id, ItemPatch(intent="sell", location="desk drawer", version=1))
    assert (changed.intent, changed.location, changed.version) == ("sell", "desk drawer", 2)
    assert inventory.events(item.id)[-1].change == "changed location, intent"
    with pytest.raises(VersionConflictError):
        inventory.update(item.id, ItemPatch(intent="give", version=1))
    assert inventory.get(item.id).intent == "sell"


def test_separating_a_component_marks_the_parent(inventory: Inventory) -> None:
    phone = inventory.create(ItemCreate(item_type="phone", intent="build"))
    camera = inventory.add_component(
        phone.id, ComponentCreate(name="camera module", condition="works")
    )
    assert camera.parent_id == phone.id
    assert camera.intent == "build"
    assert camera.item_type == "camera module"
    parent = inventory.get(phone.id)
    assert parent.components == [camera.id]
    assert parent.faults == f"camera module separated into item {camera.id}"
    assert parent.version == 2
    assert inventory.events(phone.id)[-1].change == "component separated: camera module"
    assert inventory.events(camera.id)[0].change == f"separated from item {phone.id}"


def test_delete_hides_the_item_but_keeps_its_events(inventory: Inventory) -> None:
    item = inventory.create(ItemCreate(item_type="cable"))
    inventory.delete(item.id)
    assert inventory.list_items() == []
    with pytest.raises(NotFoundError):
        inventory.get(item.id)
    with pytest.raises(NotFoundError):
        inventory.delete(item.id)
    assert [e.change for e in inventory.events(item.id)] == ["created", "deleted"]


def test_missing_items_raise(inventory: Inventory) -> None:
    with pytest.raises(NotFoundError):
        inventory.get(42)
    with pytest.raises(NotFoundError):
        inventory.create(ItemCreate(item_type="orphan", parent_id=42))


def test_store_survives_a_restart_and_refuses_a_newer_schema(settings: Settings) -> None:
    first = Inventory(settings)
    first.create(ItemCreate(item_type="kept"))
    again = Inventory(settings)
    assert [s.item_type for s in again.list_items()] == ["kept"]
    with sqlite3.connect(settings.inventory_db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(SchemaTooNewError):
        Store(settings.inventory_db_path)


def test_the_journal_mode_is_a_setting(settings: Settings) -> None:
    kept = Inventory(settings.model_copy(update={"sqlite_journal_mode": "DELETE"}))
    with kept.store.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    with Inventory(settings).store.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_a_version_one_file_is_upgraded_in_place(settings: Settings) -> None:
    path = settings.inventory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(MIGRATIONS[1])
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            "INSERT INTO items (name, item_type, intent, availability, created_at, updated_at)"
            " VALUES ('old', 'old', 'keep', 'available', 't', 't')"
        )
    Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        columns = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        assert "profile" in columns
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "measurements" in tables
    assert [s.profile for s in Inventory(settings).list_items()] == [""]


def test_a_file_left_between_two_columns_of_a_step_opens(settings: Settings) -> None:
    path = settings.inventory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for version in range(1, 12):
            conn.executescript(MIGRATIONS[version])
        # version 12 began and stopped after its first column, its version not written
        conn.execute("ALTER TABLE access_keys ADD COLUMN parent_id INTEGER")
        conn.execute("PRAGMA user_version = 11")
    Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        columns = {r[1] for r in conn.execute("PRAGMA table_info(access_keys)")}
        assert {"parent_id", "master"} <= columns


def test_a_file_that_already_has_the_scenarios_table_opens(settings: Settings) -> None:
    path = settings.inventory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for version in range(1, 13):
            conn.executescript(MIGRATIONS[version])
        # another build's step made the table and its index, its version not kept here
        conn.executescript(MIGRATIONS[13])
        conn.execute("PRAGMA user_version = 12")
    Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert {"scenarios", "scenarios_by_item"} <= names


def test_a_version_twelve_file_gets_scenarios_then_the_listing_tables(settings: Settings) -> None:
    path = settings.inventory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for version in range(1, 13):
            conn.executescript(MIGRATIONS[version])
        conn.execute("PRAGMA user_version = 12")
    Store(path)
    Store(path)  # opening again changes nothing
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 14
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert {"scenarios", "sell_details", "marketplace_events"} <= names


def test_a_file_whose_listing_step_was_numbered_thirteen_opens(settings: Settings) -> None:
    # an earlier build of the listing step wrote its tables as version 13, so the file skipped
    # the scenarios step; step 14 runs over the tables it has and adds the one it lacks
    path = settings.inventory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for version in range(1, 13):
            conn.executescript(MIGRATIONS[version])
        conn.executescript(MIGRATIONS[14].split("CREATE TABLE IF NOT EXISTS scenarios")[0])
        conn.execute("PRAGMA user_version = 13")
    Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert {"scenarios", "scenarios_by_item", "sell_details", "marketplace_events"} <= names


def test_a_step_that_fails_leaves_the_version_before_it(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = settings.inventory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for version in range(1, 12):
            conn.executescript(MIGRATIONS[version])
        conn.execute("PRAGMA user_version = 11")
    broken = "ALTER TABLE access_keys ADD COLUMN parent_id INTEGER;\nNOT A STATEMENT;"
    monkeypatch.setitem(MIGRATIONS, 12, broken)
    with pytest.raises(sqlite3.OperationalError):
        Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
        columns = {r[1] for r in conn.execute("PRAGMA table_info(access_keys)")}
        assert "parent_id" not in columns


def test_every_editable_column_has_its_fixed_update_statement() -> None:
    from app.inventory.service import EDITABLE, SET_COLUMN

    assert tuple(SET_COLUMN) == EDITABLE
    for column, sql in SET_COLUMN.items():
        assert sql.startswith("UPDATE items SET ") and "<column>" not in sql
        assert sql.split()[3] == column


def test_blank_names_and_values_are_refused(inventory: Inventory) -> None:
    item = inventory.create(ItemCreate(item_type="  USB hub  ", name="   "))
    assert (item.name, item.item_type) == ("USB hub", "USB hub")
    with pytest.raises(ValueError, match="name"):
        ItemPatch(name="   ")
    with pytest.raises(ValueError, match="item_type"):
        ItemPatch(item_type="")
    assert ItemPatch(name="  Hub  ").name == "Hub"
    with pytest.raises(ValueError, match="value"):
        FieldCreate(field="colour", value="   ")
    assert FieldCreate(field="colour", value=" black ", unit=" ").value == "black"
    assert FieldCreate(field="colour", value="black", unit=" mm ").unit == "mm"
    with pytest.raises(ValueError, match="name"):
        ComponentCreate(name=" ")
    part = ComponentCreate(name=" cable ", item_type="  ")
    assert (part.name, part.item_type) == ("cable", "")


def test_a_null_in_a_patch_means_not_given(inventory: Inventory) -> None:
    item = inventory.create(ItemCreate(item_type="hub", condition="works"))
    same = inventory.update(item.id, ItemPatch.model_validate({"condition": None, "notes": None}))
    assert (same.condition, same.version) == ("works", 1)


def test_an_owner_value_cannot_claim_to_be_observed() -> None:
    with pytest.raises(ValueError, match="not 'observed'"):
        FieldCreate(field="colour", value="black", provenance="observed")


def test_free_text_has_a_bound() -> None:
    with pytest.raises(ValueError):
        ItemCreate(item_type="x" * 201)
    with pytest.raises(ValueError):
        ItemPatch(notes="n" * 4001)
    with pytest.raises(ValueError):
        FieldCreate(field="colour", value="v" * 501)
    assert ItemCreate(notes="n" * 4000).notes


def test_a_note_field_takes_prose_and_any_other_field_a_short_value() -> None:
    assert FieldCreate(field="condition_notes", value="w " * 1500).value
    with pytest.raises(ValueError, match="at most 4000 characters"):
        FieldCreate(field="condition_notes", value="w " * 2500)
    with pytest.raises(ValueError, match="at most 500 characters"):
        FieldCreate(field="output_voltage", value="9" * 501)
    with pytest.raises(ValueError, match="at most 500 characters"):
        FieldCreate(field="output_voltage", value="9", raw="9" * 501)

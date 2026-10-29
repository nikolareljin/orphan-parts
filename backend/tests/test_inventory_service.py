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
from app.inventory.store import SCHEMA_VERSION, SchemaTooNewError, Store


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


def test_every_editable_column_has_its_fixed_update_statement() -> None:
    from app.inventory.service import EDITABLE, SET_COLUMN

    assert tuple(SET_COLUMN) == EDITABLE
    for column, sql in SET_COLUMN.items():
        assert sql.startswith("UPDATE items SET ") and "<column>" not in sql
        assert sql.split()[3] == column

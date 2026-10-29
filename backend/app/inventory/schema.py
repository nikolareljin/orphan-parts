"""Shapes of the inventory: what is stored, what the API takes and what it serves."""

from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.extract.schema import Extraction, Source

# How a value is known. An observation never goes away: a correction sits beside it.
Provenance = Literal["observed", "owner_reported", "documented", "tested", "estimated"]
# What the owner means to do with the item.
Intent = Literal["keep", "build", "sell", "give"]
# Whether a plan or a listing may count on it.
Availability = Literal["available", "reserved", "gone"]
# An observed value is proposed until the owner accepts or rejects it.
Review = Literal["proposed", "accepted", "rejected"]

FIELD_NAME = r"^[a-z][a-z0-9_]{0,63}$"
NAME_MAX = 200
VALUE_MAX = 500
TEXT_MAX = 4000


class Assertion(BaseModel):
    """One value for one field, with how it is known and whether the owner agreed."""

    id: int
    field: str
    value: str
    unit: str = ""
    provenance: Provenance
    confidence: float = Field(ge=0, le=1)
    source: Source
    raw: str = ""
    review: Review
    at: str


class Event(BaseModel):
    """One change to one item: who, when, what, and the item version it produced."""

    id: int
    item_id: int
    at: str
    actor: str
    change: str
    version: int


class ItemSummary(BaseModel):
    """The list view. Location and notes stay on the item page."""

    id: int
    name: str
    item_type: str
    profile: str
    condition: str
    intent: Intent
    availability: Availability
    parent_id: int | None
    field_count: int
    version: int
    updated_at: str


class Item(ItemSummary):
    faults: str
    tests_done: str
    accessories: str
    location: str
    notes: str
    created_at: str
    fields: dict[str, Assertion]
    assertions: list[Assertion]
    components: list[int]


class ItemCreate(BaseModel):
    """A new record, from a label reading or by hand. Everything but the type may be empty."""

    extraction: Extraction | None = None
    name: str = Field(default="", max_length=NAME_MAX)
    item_type: str = Field(default="", max_length=NAME_MAX)
    profile: str = Field(default="", max_length=NAME_MAX)
    condition: str = Field(default="", max_length=TEXT_MAX)
    faults: str = Field(default="", max_length=TEXT_MAX)
    tests_done: str = Field(default="", max_length=TEXT_MAX)
    accessories: str = Field(default="", max_length=TEXT_MAX)
    location: str = Field(default="", max_length=TEXT_MAX)
    notes: str = Field(default="", max_length=TEXT_MAX)
    intent: Intent = "keep"
    availability: Availability = "available"
    parent_id: int | None = None


def _trimmed(value: str) -> str:
    return " ".join(value.split())


def _named(value: str | None, info: ValidationInfo) -> str | None:
    """A name is trimmed and, when given, never blank."""
    if value is None:
        return None
    value = _trimmed(value)
    if not value:
        raise ValueError(f"{info.field_name} must not be blank")
    return value


class ItemPatch(BaseModel):
    """Fields the owner edits in place. ``version`` makes the write conditional."""

    name: str | None = Field(default=None, max_length=NAME_MAX)
    item_type: str | None = Field(default=None, max_length=NAME_MAX)
    profile: str | None = Field(default=None, max_length=NAME_MAX)
    condition: str | None = Field(default=None, max_length=TEXT_MAX)
    faults: str | None = Field(default=None, max_length=TEXT_MAX)
    tests_done: str | None = Field(default=None, max_length=TEXT_MAX)
    accessories: str | None = Field(default=None, max_length=TEXT_MAX)
    location: str | None = Field(default=None, max_length=TEXT_MAX)
    notes: str | None = Field(default=None, max_length=TEXT_MAX)
    intent: Intent | None = None
    availability: Availability | None = None
    version: int | None = None

    @field_validator("name", "item_type")
    @classmethod
    def _names(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info)


class FieldCreate(BaseModel):
    """A value the owner states, tested or looked up. It never replaces an observation."""

    field: str = Field(pattern=FIELD_NAME)
    value: str = Field(max_length=VALUE_MAX)
    unit: str = Field(default="", max_length=32)
    provenance: Provenance = "owner_reported"
    raw: str = Field(default="", max_length=VALUE_MAX)

    @field_validator("provenance")
    @classmethod
    def _not_observed(cls, value: Provenance) -> Provenance:
        # an observation comes from a photo through the reader; the owner states, tests or cites
        if value == "observed":
            raise ValueError("provenance must say how you know it, not 'observed'")
        return value

    @field_validator("value")
    @classmethod
    def _value(cls, value: str, info: ValidationInfo) -> str:
        return _named(value, info) or ""

    @field_validator("unit", "raw")
    @classmethod
    def _trim(cls, value: str) -> str:
        return _trimmed(value)


class ReviewChange(BaseModel):
    review: Review


class ComponentCreate(BaseModel):
    """A removable part separated into its own record under the whole device."""

    name: str = Field(max_length=NAME_MAX)
    item_type: str = Field(default="", max_length=NAME_MAX)
    condition: str = Field(default="", max_length=TEXT_MAX)
    notes: str = Field(default="", max_length=TEXT_MAX)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str, info: ValidationInfo) -> str:
        return _named(value, info) or ""

    @field_validator("item_type")
    @classmethod
    def _type(cls, value: str) -> str:
        return _trimmed(value)

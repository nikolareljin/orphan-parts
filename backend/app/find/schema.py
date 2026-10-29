"""Shapes of a missing-item search: what is needed, what a candidate shows, where it stands."""

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.extract.schema import Evidence, ReadField
from app.match.schema import MAX_VALUE_LEN, MAX_VALUES, Assessment

PROFILE = r"^$|^[a-z][a-z0-9_]{0,63}$"
CURRENCY = r"^[A-Z]{3}$"
DATE = r"^$|^\d{4}-\d{2}-\d{2}$"
TITLE_MAX = 200
LINE_MAX = 500
TEXT_MAX = 8000
NOTES_MAX = 2000
PRICE_MAX = 10_000_000

Status = Literal["open", "found", "closed"]
SourceKind = Literal["text", "screenshot", "manual"]
# Where a candidate stands; the verdict ladder maps onto these, and the owner may withdraw one.
State = Literal[
    "unassessed", "needs_evidence", "conflicting", "documented", "rejected", "withdrawn"
]


def _bounded_values(values: dict[str, str]) -> dict[str, str]:
    if len(values) > MAX_VALUES:
        raise ValueError(f"at most {MAX_VALUES} values")
    for key, value in values.items():
        if len(key) > 64 or len(value) > MAX_VALUE_LEN:
            raise ValueError(f"value for {key[:64]!r} is too long")
    return values


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _a_day_that_was(value: str) -> str:
    if not value:
        return value
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("a real date, YYYY-MM-DD") from exc
    if day > datetime.now(UTC).date():
        raise ValueError("cannot be in the future")
    return value


class SearchCreate(BaseModel):
    """What is needed: another item's requirements, or values written in, under a profile."""

    need_item_id: int | None = None
    profile: str = Field(default="", pattern=PROFILE, description="taken from the item when given")
    title: str = Field(max_length=TITLE_MAX, description="what is looked for, in a line")
    spec: dict[str, str] = Field(default={}, description="rule key to needed value")
    radius_km: int | None = Field(default=None, ge=0, le=20_000)
    max_price: float | None = Field(default=None, ge=0, le=PRICE_MAX)
    currency: str = Field(default="USD", pattern=CURRENCY)
    budget_left: float | None = Field(default=None, ge=0, le=PRICE_MAX)
    notes: str = Field(default="", max_length=NOTES_MAX)

    @field_validator("title")
    @classmethod
    def _titled(cls, value: str) -> str:
        value = _one_line(value)
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("spec")
    @classmethod
    def _bounded(cls, values: dict[str, str]) -> dict[str, str]:
        return _bounded_values(values)


class SearchPatch(BaseModel):
    status: Status | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class Search(BaseModel):
    id: int
    need_item_id: int | None
    profile: str
    title: str
    spec: dict[str, str]
    radius_km: int | None
    max_price: float | None
    currency: str
    budget_left: float | None
    notes: str
    status: Status
    handoff_url: str = Field(
        description="the Marketplace search the owner runs; nothing is fetched"
    )
    candidates: int
    created_at: str
    updated_at: str


class ListingReading(BaseModel):
    """Strict output schema of a listing-text call: every property required, no extras."""

    title: str
    asking_price: str
    currency: str
    location: str
    included: str
    fields: list[ReadField]


class CandidateCreate(BaseModel):
    """A listing the owner brought back: its text, a screenshot, or values typed in; the day it
    was seen; and what the listing said about price, place and what comes with it."""

    source_kind: SourceKind = "text"
    text: str = Field(default="", max_length=TEXT_MAX)
    observed_on: str = Field(
        default="", pattern=DATE, description="the day it was seen; today when empty"
    )
    asking_price: str = Field(default="", max_length=40)
    currency: str = Field(default="USD", pattern=CURRENCY)
    location: str = Field(default="", max_length=120)
    included_parts: str = Field(default="", max_length=LINE_MAX)
    url: str = Field(default="", max_length=LINE_MAX, description="kept as given, never fetched")
    values: dict[str, str] = Field(default={}, description="fields typed in, by rule key")
    note: str = Field(default="", max_length=LINE_MAX)

    @field_validator("observed_on")
    @classmethod
    def _seen(cls, value: str) -> str:
        return _a_day_that_was(value)

    @field_validator("text", "note")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return value.strip()

    @field_validator("asking_price", "location", "included_parts", "url")
    @classmethod
    def _lines(cls, value: str) -> str:
        return _one_line(value)

    @field_validator("values")
    @classmethod
    def _bounded(cls, values: dict[str, str], info: ValidationInfo) -> dict[str, str]:
        return _bounded_values(values)


class Candidate(BaseModel):
    id: int
    search_id: int
    source_kind: SourceKind
    observed_on: str
    expires_on: str = Field(description="when the observation is too old to trust")
    expired: bool
    asking_price: str
    currency: str
    location: str
    included_parts: str
    url: str
    title: str
    text: str
    note: str
    fields: dict[str, Evidence]
    warnings: list[str]
    assessment: Assessment | None
    state: State
    questions: list[str]
    model: str
    from_fixture: bool
    cost_usd: float
    created_at: str
    assessed_at: str


class SellerQuestions(BaseModel):
    """What to ask the seller, as a message the owner can send; made by the rules, not a model."""

    candidate_id: int
    subject: str
    message: str
    questions: list[str]

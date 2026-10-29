"""Shapes of price guidance: what the model found, what the owner reported, what is shown."""

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CURRENCY = r"^[A-Z]{3}$"
DATE = r"^\d{4}-\d{2}-\d{2}$"
COUNTRY = r"^$|^[A-Z]{2}$"
NOTE_MAX = 200
PRICE_MAX = 10_000_000

# The four quantities, never merged: what is asked, what was paid, what the owner knows, what
# the model thinks. An asking price is never a sold one.
Kind = Literal["asking", "sold", "reported", "estimate"]
Seen = Literal["asking", "sold"]


class Comparable(BaseModel):
    """One listing or sale the model found, with the page it rests on."""

    kind: Seen
    title: str
    price: float
    currency: str
    condition: str
    observed: str = Field(description="the date on the page, or the day it was seen")
    source_url: str
    source_title: str


class Findings(BaseModel):
    """Strict output schema of a price call: every property required, no extras."""

    comparables: list[Comparable]
    estimate_low: float
    estimate_high: float
    estimate_typical: float
    currency: str
    basis: str
    caveats: list[str]


class PriceRequest(BaseModel):
    currency: str = Field(default="USD", pattern=CURRENCY)
    country: str = Field(default="", pattern=COUNTRY, description="ISO 3166-1, for local results")
    city: str = Field(default="", max_length=80)

    @field_validator("city")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join(value.split())


class PriceReportCreate(BaseModel):
    """A sale the owner knows of: theirs, or one they saw happen. Never mixed with the rest."""

    price: float = Field(gt=0, le=PRICE_MAX)
    currency: str = Field(default="USD", pattern=CURRENCY)
    sold_on: str = Field(pattern=DATE)
    note: str = Field(default="", max_length=NOTE_MAX)

    @field_validator("sold_on")
    @classmethod
    def _a_day_that_was(cls, value: str) -> str:
        # a real calendar day, and not one still to come: a sale is something that happened
        try:
            day = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("sold_on must be a real date, YYYY-MM-DD") from exc
        if day > datetime.now(UTC).date():
            raise ValueError("sold_on cannot be in the future")
        return value


class PriceReport(BaseModel):
    id: int
    item_id: int
    price: float
    currency: str
    sold_on: str
    note: str
    at: str


class Quantity(BaseModel):
    kind: Kind
    label: str
    count: int
    low: float | None
    high: float | None
    typical: float | None = Field(description="the median, or the estimate's typical")
    currency: str
    basis: str = Field(description="where the figures come from and when")


class Strategy(BaseModel):
    name: Literal["quick_sale", "typical", "patient"]
    label: str
    price: float | None
    note: str


class Source(BaseModel):
    url: str
    title: str
    observed: str


class PartsComparison(BaseModel):
    """Whole against parts: the parts' own guidance, summed; nothing is invented per part."""

    components: int
    priced: int
    sum_typical: float | None
    whole_typical: float | None
    note: str


class Guidance(BaseModel):
    id: int
    item_id: int
    version: int = Field(description="per item; a new request bumps it")
    item_version: int
    stale: bool = Field(description="the item changed since the guidance was written")
    currency: str
    quantities: list[Quantity]
    comparables: list[Comparable] = Field(description="only those a search result backs")
    dropped: int = Field(description="lines the model wrote that no search result backs")
    sources: list[Source]
    estimate_label: Literal["estimate"]
    strategies: list[Strategy]
    weak: bool
    weak_reason: str
    caveats: list[str]
    parts: PartsComparison | None
    searches: int
    model: str
    from_fixture: bool
    cost_usd: float
    at: str

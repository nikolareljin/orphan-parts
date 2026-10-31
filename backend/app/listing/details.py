"""What the owner adds before a listing is drafted ("Tell us more"). Stored on the item, one
version per save. The lowest acceptable price and the reason for selling are the owner's own;
they never reach the model or the listing text."""

import re
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.listing.marketplace import personal_details

Included = Literal["stand", "cables", "power_cord", "box", "manual", "remote"]
INCLUDED_LABELS: dict[str, str] = {
    "stand": "stand",
    "cables": "cables",
    "power_cord": "power cord",
    "box": "original box",
    "manual": "manual",
    "remote": "remote",
}
Handover = Literal["pickup", "shipping", "either"]
DataState = Literal["none", "wiped", "not_wiped"]
PRIVATE_FIELDS = frozenset({"lowest_price", "reason"})
WORDS_MAX = 1000
LINE_MAX = 200
AREA_MAX = 80
PRICE_MAX = 1_000_000
_ZIP = re.compile(r"^\d{5}(?:-\d{4})?$")
DATE = r"^\d{4}-\d{2}-\d{2}$"


def _one_line(value: str) -> str:
    return " ".join(value.split())


class SellDetails(BaseModel):
    """What the owner says about the item for a listing. Every field may be left empty."""

    condition_words: str = Field(
        default="", max_length=WORDS_MAX, description="the condition in the owner's words"
    )
    included: list[Included] = Field(default_factory=list)
    included_other: str = Field(default="", max_length=LINE_MAX)
    faults: str = Field(
        default="", max_length=WORDS_MAX, description="known faults and cosmetic issues"
    )
    untested: str = Field(default="", max_length=LINE_MAX, description="what was not tested")
    data: DataState = Field(
        default="none", description="none: stores no accounts or files; wiped; not_wiped"
    )
    reason: str = Field(
        default="", max_length=LINE_MAX, description="private: never in the listing text"
    )
    handover: Handover = "pickup"
    area: str = Field(
        default="",
        max_length=AREA_MAX,
        description="city, ZIP or neighborhood; never a street address",
    )
    asking_price: float | None = Field(default=None, ge=0, le=PRICE_MAX)
    lowest_price: float | None = Field(
        default=None, ge=0, le=PRICE_MAX, description="private: never in the listing text"
    )
    availability: str = Field(default="", max_length=LINE_MAX)

    @field_validator("included")
    @classmethod
    def _once_each(cls, value: list[Included]) -> list[Included]:
        return list(dict.fromkeys(value))

    @field_validator("included_other", "untested", "reason", "area", "availability")
    @classmethod
    def _line(cls, value: str) -> str:
        return _one_line(value)

    @field_validator("condition_words", "faults")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("area")
    @classmethod
    def _not_an_address(cls, value: str) -> str:
        # a ZIP is fine; anything else that starts with a number reads as a house number
        if value and not _ZIP.match(value) and (value[0].isdigit() or personal_details(value)):
            raise ValueError("area: a city, ZIP or neighborhood, not a street address")
        return value

    @field_validator("condition_words", "included_other", "faults", "untested", "availability")
    @classmethod
    def _no_contact(cls, value: str, info: ValidationInfo) -> str:
        found = personal_details(value)
        if found:
            raise ValueError(
                f"{info.field_name}: leave out {' and '.join(found)};"
                " buyers write through Marketplace"
            )
        return value

    @model_validator(mode="after")
    def _lowest_under_asking(self) -> "SellDetails":
        if (
            self.asking_price is not None
            and self.lowest_price is not None
            and self.lowest_price > self.asking_price
        ):
            raise ValueError("the lowest price is above the asking price")
        return self

    def included_text(self) -> str:
        parts = [INCLUDED_LABELS[k] for k in self.included]
        if self.included_other:
            parts.append(self.included_other)
        return ", ".join(parts)

    def handover_line(self, mode: str) -> str:
        where = f" in {self.area}" if self.area else ""
        if mode == "give" or self.handover == "pickup":
            return f"Local pickup{where}."
        if self.handover == "shipping":
            return "Shipping only." if not self.area else f"Ships from {self.area}."
        return f"Local pickup{where}, or shipping."


class SellDetailsRecord(BaseModel):
    item_id: int
    version: int = Field(description="per item; each save is a new version")
    details: SellDetails
    at: str


def _a_day_that_was(value: str) -> str:
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("a real date, YYYY-MM-DD") from exc
    if day > datetime.now(UTC).date():
        raise ValueError("the date cannot be in the future")
    return value


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class Listed(BaseModel):
    """The owner posted it on Marketplace."""

    on: str = Field(default_factory=_today, pattern=DATE)
    price: float = Field(ge=0, le=PRICE_MAX)
    url: str = Field(default="", max_length=500, description="the listing's address, pasted")

    @field_validator("on")
    @classmethod
    def _day(cls, value: str) -> str:
        return _a_day_that_was(value)

    @field_validator("url")
    @classmethod
    def _facebook(cls, value: str) -> str:
        value = value.strip()
        if value and not re.match(
            r"^https://(?:www\.|m\.|web\.)?facebook\.com/marketplace/\S+$", value
        ):
            raise ValueError("url: a https://www.facebook.com/marketplace/... address")
        return value


class Sold(BaseModel):
    on: str = Field(default_factory=_today, pattern=DATE)
    price: float = Field(gt=0, le=PRICE_MAX)

    @field_validator("on")
    @classmethod
    def _day(cls, value: str) -> str:
        return _a_day_that_was(value)


class Given(BaseModel):
    on: str = Field(default_factory=_today, pattern=DATE)

    @field_validator("on")
    @classmethod
    def _day(cls, value: str) -> str:
        return _a_day_that_was(value)


Outcome = Literal["listed", "sold", "given"]


class MarketplaceEvent(BaseModel):
    id: int
    item_id: int
    kind: Outcome
    on: str
    price: float | None
    url: str
    at: str


class MarketplaceStatus(BaseModel):
    item_id: int
    state: Literal["", "listed", "sold", "given"] = Field(description="the latest event's kind")
    events: list[MarketplaceEvent]

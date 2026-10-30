"""The demo set, as data: which photos, texts and notes make up the walkthrough, so one run
records every model answer the set needs and the same run replays them at no cost."""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.find.schema import CURRENCY
from app.inventory.schema import PROFILE_ID, Availability, Intent
from app.listing.checklists import Mode
from app.projects.schema import Preferences

KEY = r"^[a-z][a-z0-9_]{0,63}$"


class DemoItem(BaseModel):
    """One thing in the drawer: its photos go through extraction and become an item."""

    key: str = Field(pattern=KEY)
    name: str = Field(min_length=1, max_length=200)
    item_type: str = Field(default="", max_length=200)
    profile: str = Field(default="", pattern=PROFILE_ID)
    photos: list[str] = Field(default=[], description="relative to the set file; JPEG or PNG")
    accept_all: bool = Field(default=True, description="confirm every observed value")
    condition: str = ""
    faults: str = ""
    tests_done: str = ""
    accessories: str = ""
    intent: Intent = "keep"
    availability: Availability = "available"
    fields: dict[str, str] = Field(default={}, description="owner values, by field")
    voice_note: str = Field(default="", description="a WAV file, relative to the set file")
    draft: Mode | None = Field(default=None, description="write a sell or a give draft")
    holds_data: bool = False
    asking_price: str = ""
    price: bool = Field(default=False, description="ask for price guidance")

    @field_validator("photos")
    @classmethod
    def _some(cls, values: list[str]) -> list[str]:
        if len(values) > 4:
            raise ValueError("at most four photos per item")
        return values


class DemoListing(BaseModel):
    text: str = Field(description="a listing's text, or @file relative to the set file")
    observed_on: str = ""
    asking_price: str = ""
    currency: str = Field(default="USD", pattern=CURRENCY)
    location: str = ""


class DemoSearch(BaseModel):
    key: str = Field(pattern=KEY)
    need: str = Field(default="", description="the key of the item that needs it")
    profile: str = Field(default="", pattern=PROFILE_ID)
    title: str = Field(min_length=1, max_length=200)
    spec: dict[str, str] = {}
    max_price: float | None = None
    currency: str = Field(default="USD", pattern=CURRENCY)
    listings: list[DemoListing] = []


class DemoPropose(BaseModel):
    preferences: Preferences = Preferences()
    count: int = Field(default=3, ge=1, le=5)
    note: str = ""


class DemoSet(BaseModel):
    """The whole walkthrough. Keys are unique; a search's need names an item of the set."""

    title: str = "the demo set"
    items: list[DemoItem] = []
    searches: list[DemoSearch] = []
    propose: DemoPropose | None = None
    currency: str = Field(default="USD", pattern=CURRENCY)
    country: str = Field(default="", description="ISO 3166-1, for price guidance")

    @field_validator("items")
    @classmethod
    def _unique_items(cls, items: list[DemoItem]) -> list[DemoItem]:
        keys = [i.key for i in items]
        if len(keys) != len(set(keys)):
            raise ValueError("item keys repeat")
        return items

    def check(self) -> None:
        """What the services would refuse is refused here, before anything is loaded or spent:
        an item's texts and fields must pass the inventory's own rules."""
        from app.inventory.schema import FieldCreate, ItemCreate

        for i in self.items:
            try:
                ItemCreate(
                    name=i.name,
                    item_type=i.item_type or "item",
                    condition=i.condition,
                    faults=i.faults,
                    tests_done=i.tests_done,
                    accessories=i.accessories,
                )
                for field, value in i.fields.items():
                    FieldCreate(field=field, value=value)
            except ValueError as exc:
                raise ValueError(f"item {i.key!r}: {exc}") from exc
        keys = {i.key for i in self.items}
        for s in self.searches:
            if s.need and s.need not in keys:
                raise ValueError(f"search {s.key!r} needs {s.need!r}, which is not an item")
            if not s.need and not s.profile:
                raise ValueError(f"search {s.key!r} needs an item or a profile")


class Outcome(BaseModel):
    """What one run did, in counts, and what it skipped with the reason."""

    items: int = 0
    photos: int = 0
    voice_notes: int = 0
    drafts: int = 0
    guidances: int = 0
    searches: int = 0
    candidates: int = 0
    projects: int = 0
    skipped: list[str] = []
    cost_usd: float = 0.0
    mode: str = ""

    def lines(self) -> list[str]:
        out = [
            f"mode {self.mode}: {self.items} item(s) from {self.photos} photo(s),"
            f" {self.voice_notes} voice note(s), {self.drafts} draft(s), {self.guidances}"
            f" guidance(s), {self.searches} search(es) with {self.candidates} candidate(s),"
            f" {self.projects} project(s); {self.cost_usd:.4f} USD"
        ]
        out += [f"skipped: {s}" for s in self.skipped]
        return out


def set_dir(path: Path) -> Path:
    return path.parent

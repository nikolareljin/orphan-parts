"""The demo set, as data: which photos, texts and notes make up the walkthrough, so one run
records every model answer the set needs and the same run replays them at no cost."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.decide.schema import NOTE_MAX, Choice
from app.find.schema import CURRENCY
from app.inventory.schema import PROFILE_ID, Availability, Intent
from app.listing.checklists import Mode
from app.measure.schema import FEATURE_KEY, ImageSize, Point, Reference
from app.projects.schema import Preferences

KEY = r"^[a-z][a-z0-9_]{0,63}$"


class ExpectFit(BaseModel):
    """What the rules should say when this item is checked against another of the set."""

    against: str = Field(pattern=KEY, description="the key of the item that is the need")
    verdict: Literal["fits", "conflict"]
    values: dict[str, str] = Field(
        default={},
        description="the need's values in the rule's terms, when its own fields are named"
        " otherwise (a vacuum's wand outer diameter is the needed opening inner diameter)",
    )


class Expect(BaseModel):
    """What an evaluation run scores the item against. Every part is optional."""

    fields: dict[str, str] = Field(
        default={}, description="values the reading should give, by field, with the unit"
    )
    fit: ExpectFit | None = None
    proposals_min: int | None = Field(
        default=None, ge=0, description="kept proposals that should allocate this item"
    )


class DemoMeasurement(BaseModel):
    """A feature measured on one of the item's photos, as the owner marks it under Measure a
    feature: geometry computes the value, no model is called, and an accepted capture is the
    item's value with the source ``measurement``."""

    photo: str = Field(description="relative to the set file; the photo the marks are on")
    feature: str = Field(pattern=FEATURE_KEY)
    image: ImageSize | None = Field(
        default=None, description="the size the marks refer to; the photo's own when left out"
    )
    reference: Reference
    points: list[Point] = Field(min_length=2, max_length=2)
    straight_on: bool = Field(
        default=False, description="the owner's statement; a two-point scale needs it"
    )


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
    measurements: list[DemoMeasurement] = Field(
        default=[], description="features measured on the item's photos, in this order"
    )
    voice_note: str = Field(default="", description="a WAV file, relative to the set file")
    draft: Mode | None = Field(default=None, description="write a sell or a give draft")
    holds_data: bool = False
    asking_price: str = ""
    price: bool = Field(default=False, description="ask for price guidance")
    picture: str = Field(
        default="",
        max_length=200,
        description="draw a picture of the item as this use (a template id or a few words);"
        " fixture mode shows it only when a recording of that drawing is kept",
    )
    decide: bool = Field(
        default=False,
        description="write the Decide cards (keep and fix, reuse, sell or give away) once its"
        " drafts, picture and price guidance are kept; only a recording of this very request"
        " answers in fixture mode",
    )
    ideas: bool = Field(
        default=False,
        description="ask what it is good for (the ideas under Decide); only a recording of"
        " this very request answers in fixture mode",
    )
    reuse_picture: bool = Field(
        default=False,
        description="draw the first reuse card of its Decide cards with Draw it (needs"
        " decide); only a recording of this very drawing answers in fixture mode",
    )
    decision: Choice | None = Field(
        default=None,
        description="the plan the owner chose, recorded last: keep_fix, keep_spare,"
        " keep_build, sell, give or not_worth",
    )
    decision_note: str = Field(
        default="", max_length=NOTE_MAX, description="the owner's note said with the decision"
    )
    expect: Expect | None = Field(default=None, description="what an evaluation run scores")
    parent_photos: list[str] = Field(
        default=[],
        description="photos of the device a part came from (its label first), read once as a"
        " label and kept as the item's device photos, apart from its own",
    )
    parent_device: str = Field(
        default="", max_length=500, description="the owner's words about that device"
    )
    parent_device_model: str = Field(
        default="",
        max_length=200,
        description="the device's model as its label states it; saved as typed while the"
        " reading of parent_photos is not recorded yet",
    )

    @field_validator("photos", "parent_photos")
    @classmethod
    def _some(cls, values: list[str]) -> list[str]:
        if len(values) > 4:
            raise ValueError("at most four photos per item")
        return values


DATE = r"^$|^\d{4}-\d{2}-\d{2}$"


class DemoListing(BaseModel):
    text: str = Field(description="a listing's text, or @file relative to the set file")
    observed_on: str = Field(
        default="",
        pattern=DATE,
        description="when the listing was seen; empty = the day it is loaded, which keeps it fresh",
    )
    asking_price: str = ""
    currency: str = Field(default="USD", pattern=CURRENCY)
    location: str = ""


class DemoSearch(BaseModel):
    key: str = Field(pattern=KEY)
    need: str = Field(default="", description="the key of the item that needs it")
    profile: str = Field(default="", pattern=PROFILE_ID)
    title: str = Field(min_length=1, max_length=200)
    spec: dict[str, str] = {}
    max_price: float | None = Field(default=None, ge=0, le=10_000_000)
    currency: str = Field(default="USD", pattern=CURRENCY)
    listings: list[DemoListing] = []
    web: bool = Field(
        default=False,
        description="run Search the web once the items are loaded; only a recording of this very"
        " request answers in fixture mode",
    )
    plan: bool = Field(
        default=False,
        description="write the search plan (phrasings with their Marketplace links, the match"
        " pattern, the words that rule a listing out) after its listings and web finds; only a"
        " recording of this very request answers in fixture mode",
    )


class DemoRound(BaseModel):
    """One more proposal call after the first, steered by its own note."""

    count: int = Field(default=3, ge=1, le=5)
    note: str = Field(min_length=1, max_length=2000)


class DemoFill(BaseModel):
    """An item of the set put on a requirement a kept project left open, as the owner fills it;
    the rules check that it is usable and of a kind the requirement takes."""

    template: str = Field(pattern=KEY, description="the first kept project of this template")
    requirement: str = Field(pattern=KEY)
    item: str = Field(pattern=KEY, description="the key of the item of the set")
    why: str = Field(default="", max_length=200)


class DemoPropose(BaseModel):
    preferences: Preferences = Preferences()
    count: int = Field(default=3, ge=1, le=5)
    note: str = ""
    pictures: bool = Field(
        default=False,
        description="draw each kept project with Draw it; only a recording of this very"
        " drawing answers in fixture mode",
    )
    packs: bool = Field(
        default=False,
        description="select each kept project its items allow (one whose item another selected"
        " project already counts on stays proposed) and write its build pack; the rules write"
        " it, no model is asked",
    )
    rounds: list[DemoRound] = Field(
        default=[], max_length=5, description="further proposal calls, each with its note"
    )
    fill: list[DemoFill] = Field(
        default=[], description="requirements filled by the owner before the drawings"
    )
    select: list[str] = Field(
        default=[],
        description="templates whose first kept project is selected, in this order, each with"
        " its build pack; given, it is what is selected instead of what ``packs`` would take",
    )
    plan_missing: bool = Field(
        default=False,
        description="for each project ``select`` names, every requirement still open becomes a"
        " search with its plan (the Marketplace search links)",
    )
    views: list[str] = Field(
        default=[],
        max_length=4,
        description="more drawings of each project ``select`` names, one per view (in its"
        " room, a close-up of the parts): each its own request, so its own recording",
    )

    @field_validator("select")
    @classmethod
    def _templates(cls, values: list[str]) -> list[str]:
        for value in values:
            if not re.fullmatch(KEY, value):
                raise ValueError(f"{value!r} is not a template id")
        if len(values) != len(set(values)):
            raise ValueError("a template is selected twice")
        return values

    @field_validator("views")
    @classmethod
    def _views(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(v.split()) for v in values]
        if any(not v for v in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("each view is said once, in a few words")
        return cleaned


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

    @field_validator("searches")
    @classmethod
    def _unique_searches(cls, searches: list[DemoSearch]) -> list[DemoSearch]:
        keys = [s.key for s in searches]
        if len(keys) != len(set(keys)):
            raise ValueError("search keys repeat")
        return searches

    def files(self) -> list[str]:
        """Every file the set names, relative to the set file."""
        out: list[str] = []
        for i in self.items:
            out += i.photos + i.parent_photos + [m.photo for m in i.measurements]
            if i.voice_note:
                out.append(i.voice_note)
        for s in self.searches:
            out += [li.text[1:] for li in s.listings if li.text.startswith("@")]
        return out

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
        for i in self.items:
            if i.expect is not None and i.expect.fit is not None:
                if i.expect.fit.against not in keys:
                    raise ValueError(
                        f"item {i.key!r} expects a fit against {i.expect.fit.against!r},"
                        " which is not an item"
                    )
                if i.expect.fit.against == i.key:
                    raise ValueError(f"item {i.key!r} expects a fit against itself")
        if self.propose is not None:
            from app.projects.templates import Templates

            known = set(Templates().ids())
            for template in self.propose.select:
                if template not in known:
                    raise ValueError(f"proposals select {template!r}, which is not a template")
            for f in self.propose.fill:
                if f.item not in keys:
                    raise ValueError(f"a fill names {f.item!r}, which is not an item")
        for s in self.searches:
            if s.need and s.need not in keys:
                raise ValueError(f"search {s.key!r} needs {s.need!r}, which is not an item")
            if not s.need and not s.profile:
                raise ValueError(f"search {s.key!r} needs an item or a profile")
        # a file the set names stays beside the set: nothing above it is ever read or sent
        for name in self.files():
            parts = Path(name).parts
            if not name or Path(name).is_absolute() or ".." in parts:
                raise ValueError(f"{name!r}: a file of the set is named relative to it, inside it")


class Outcome(BaseModel):
    """What one run did, in counts, and what it skipped with the reason."""

    items: int = 0
    photos: int = 0
    voice_notes: int = 0
    measurements: int = Field(default=0, description="features measured on the items' photos")
    drafts: int = 0
    guidances: int = 0
    searches: int = 0
    candidates: int = 0
    web_finds: int = 0
    projects: int = 0
    pictures: int = 0
    cards: int = Field(default=0, description="Decide cards written")
    ideas: int = Field(default=0, description="answers to what an item is good for")
    decisions: int = 0
    plans: int = Field(default=0, description="search plans written")
    packs: int = Field(default=0, description="build packs written for selected projects")
    checked: int = Field(default=0, description="photos checked for private details")
    hidden: int = Field(default=0, description="areas found on them, blacked out when shared")
    skipped: list[str] = []
    unrecorded: list[str] = Field(
        default=[],
        description="what fixture mode leaves out because nothing is recorded for it yet (a"
        " picture named in the set before a record run); not a skip",
    )
    cost_usd: float = 0.0
    mode: str = ""
    stub_answers: int = Field(
        default=0,
        description="answers from an operation's stub rather than a recording of this set",
    )

    def lines(self) -> list[str]:
        out = [
            f"mode {self.mode}: {self.items} item(s) from {self.photos} photo(s),"
            f" {self.voice_notes} voice note(s), {self.measurements} measurement(s),"
            f" {self.drafts} draft(s), {self.guidances}"
            f" guidance(s), {self.searches} search(es) with {self.candidates} candidate(s)"
            f" and {self.web_finds} web find(s), {self.projects} project(s),"
            f" {self.pictures} picture(s); {self.cost_usd:.4f} USD"
        ]
        if self.cards or self.ideas or self.decisions or self.plans or self.packs:
            out.append(
                f"{self.cards} set(s) of Decide cards, {self.ideas} answer(s) of ideas,"
                f" {self.decisions} decision(s), {self.plans} search plan(s),"
                f" {self.packs} build pack(s)"
            )
        if self.checked:
            out.append(
                f"{self.checked} photo(s) checked for private details,"
                f" {self.hidden} area(s) to black out when shared"
            )
        if self.stub_answers:
            out.append(
                f"{self.stub_answers} answer(s) came from an operation's stub, not a recording"
                " of this set: record the fixtures with these files and settings, or expect"
                " the stub's words on the cards"
            )
        out += [f"skipped: {s}" for s in self.skipped]
        out += [f"not recorded yet: {u}" for u in self.unrecorded]
        return out


def set_dir(path: Path) -> Path:
    return path.parent

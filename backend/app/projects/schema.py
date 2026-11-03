"""Shapes of build and reuse: what the owner prefers, what a template asks for, what the model
proposes, and what a project becomes once items are allocated."""

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.ops.door import for_visitor
from app.privacy.text import mask_text
from app.projects.skills import STARTER_SKILLS, RatedSkill, rated_skills

KEY = r"^[a-z][a-z0-9_]{0,63}$"
CURRENCY = r"^[A-Z]{3}$"
TEXT_MAX = 2000
LINE_MAX = 200
PRICE_MAX = 10_000_000
DATE = r"^\d{4}-\d{2}-\d{2}$"

Effort = Literal["low", "medium", "high"]
Purchase = Literal["used", "new", "either"]
Status = Literal["proposed", "shortlisted", "selected", "building", "done", "abandoned"]
RequirementKind = Literal["item", "capability"]
RequirementState = Literal["pass", "unknown"]


class Preferences(BaseModel):
    """What the owner wants from a build and what they can do: a few answers, kept once, read by
    every proposal and by the scenarios on an item. The skills are rated; a plain name, as the
    record was kept before the ratings, reads as ``some``."""

    interests: str = Field(default="", max_length=TEXT_MAX)
    effort: Effort = "medium"
    skills: list[RatedSkill] = Field(default=[], max_length=len(STARTER_SKILLS) + 20)
    tools: str = Field(default="", max_length=TEXT_MAX)
    opens_devices: bool = False
    budget: float | None = Field(default=None, ge=0, le=PRICE_MAX)
    currency: str = Field(default="USD", pattern=CURRENCY)
    radius_km: int | None = Field(default=None, ge=0, le=20_000)
    purchase: Purchase = "used"

    @field_validator("skills", mode="before")
    @classmethod
    def _rated(cls, values: object) -> object:
        return rated_skills(values) if isinstance(values, list) else values

    # the owner's budget and how far they travel are left out for the demo visitor; the skills,
    # the interests and the rest are what the profile shows
    @field_serializer("budget", "radius_km")
    def _owner_numbers(self, value: float | None) -> float | None:
        return None if for_visitor() else value


class TemplateRequirement(BaseModel):
    key: str = Field(pattern=KEY)
    label: str
    kind: RequirementKind = "item"
    item_types: list[str] = Field(default=[], description="what in the inventory can fill it")
    profile: str = Field(default="", description="the profile a search for it runs under")
    blocking: bool = True


class Cost(BaseModel):
    low: float = Field(ge=0)
    high: float = Field(ge=0)
    currency: str = Field(default="USD", pattern=CURRENCY)


class Template(BaseModel):
    """A project kept as data: what it is for, what it needs, what it takes."""

    id: str = Field(pattern=KEY)
    label: str
    goal: str
    result: str
    effort: Effort
    skills: list[str] = []
    opens_devices: bool = False
    typical_cost: Cost
    requirements: list[TemplateRequirement]
    steps: list[str] = []
    safety: list[str] = []
    sources: list[str] = Field(default=[], description="guidance by name; nothing invented")


class TemplateSummary(BaseModel):
    id: str
    label: str
    goal: str
    effort: Effort
    requirements: list[str]


class ProposedAllocation(BaseModel):
    requirement: str
    item_id: int = Field(default=0, description="the item's id; 0 when only the name is known")
    item_name: str = Field(default="", description="the item's name as listed")
    why: str


class Proposal(BaseModel):
    template: str
    title: str
    result: str
    allocations: list[ProposedAllocation]
    missing: list[str] = Field(description="requirement keys the inventory does not fill")
    effort: Effort
    spend_estimate: float
    unknowns: list[str]


class ProposalSet(BaseModel):
    """Strict output schema of a proposal call: every property required, no extras."""

    proposals: list[Proposal]


class ProposeRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=5)
    note: str = Field(default="", max_length=TEXT_MAX, description="anything to add this time")

    @field_validator("note")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return value.strip()


class Allocation(BaseModel):
    item_id: int
    item_name: str
    requirement: str
    committed: bool
    why: str


class Requirement(BaseModel):
    key: str
    label: str
    kind: RequirementKind
    blocking: bool
    state: RequirementState
    item_id: int | None
    search_id: int | None = Field(description="the search opened for it, when missing")
    profile: str


class OutcomeBase(BaseModel):
    """What was built and how it was tested: the owner's record, in their words."""

    configuration: str = Field(min_length=1, max_length=TEXT_MAX)
    test: str = Field(min_length=1, max_length=TEXT_MAX)
    tested_on: str = Field(pattern=DATE)
    working: bool
    limitations: str = Field(default="", max_length=TEXT_MAX)

    @field_validator("configuration", "test")
    @classmethod
    def _said(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("limitations")
    @classmethod
    def _trimmed_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tested_on")
    @classmethod
    def _a_real_day(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("tested_on must be a real date, YYYY-MM-DD") from exc
        return value


class OutcomeCreate(OutcomeBase):
    """The record as sent: a day that has happened, by the clock of the host."""

    @field_validator("tested_on")
    @classmethod
    def _a_day_that_was(cls, value: str) -> str:
        if date.fromisoformat(value) > datetime.now(UTC).date():
            raise ValueError("tested_on cannot be in the future")
        return value


class Outcome(OutcomeBase):
    """The record as kept: read back as written, whatever the clock says since."""

    recorded_at: str
    shared: bool = False


class ShareChange(BaseModel):
    shared: bool


class ShareText(BaseModel):
    text: str


class ProgressChange(BaseModel):
    step: int = Field(ge=0, description="the step's position, from 0")
    done: bool


class Project(BaseModel):
    id: int
    template: str
    title: str
    status: Status
    version: int
    result: str
    requirements: list[Requirement]
    allocations: list[Allocation]
    effort: Effort
    skills: list[str]
    spend_estimate: float
    currency: str
    unknowns: list[str]
    sources: list[str]
    steps: list[str]
    safety: list[str]
    dropped: list[str] = Field(description="lines the model wrote that the inventory does not back")
    progress: list[bool] = Field(default=[], description="one flag per step")
    outcome: Outcome | None = None
    model: str
    from_fixture: bool
    cost_usd: float
    created_at: str
    updated_at: str

    # what the model wrote that the inventory does not back may name an item the owner keeps
    # private: left out for the demo visitor
    @field_serializer("dropped")
    def _owner_dropped(self, value: list[str]) -> list[str]:
        return [] if for_visitor() else value

    # the outcome is the owner's record: the demo visitor sees it only once it is shared
    @field_serializer("outcome")
    def _shared_outcome(self, value: Outcome | None) -> Outcome | None:
        if for_visitor() and value is not None and not value.shared:
            return None
        return value


class Budget(BaseModel):
    """What the selected set spends against the budget; nothing is committed twice."""

    budget: float | None
    currency: str
    committed_spend: float
    remaining: float | None
    selected: int

    # what the owner has to spend is theirs: left out for the demo visitor
    @field_serializer("budget", "remaining")
    def _owner_budget(self, value: float | None) -> float | None:
        return None if for_visitor() else value


class ProjectList(BaseModel):
    projects: list[Project]
    budget: Budget


class Pack(BaseModel):
    """One written build pack; stale once the project, an item on it or the budget changed."""

    id: int
    project_id: int
    version: int
    digest: str
    stale: bool
    markdown: str
    created_at: str

    # for the demo visitor, the pack without the owner's budget line, spoken notes, searches
    # and outcome section (a shared outcome is on the project itself)
    @field_serializer("markdown")
    def _visitor_markdown(self, value: str) -> str:
        return visitor_markdown(value) if for_visitor() else value


# The lines of a pack the demo visitor never reads: the owner's budget, the outcome section,
# the condition notes (a voice note is kept there, as the owner said it) and, under what is
# still needed, the search opened for it (made from values, so the owner's: its title, its top
# price, which is the budget left, and its candidates).
BUDGET_LINE = "Across the selected projects: "
OUTCOME_HEADING = "## Outcome"
INVENTORY_HEADING = "## From the inventory"
NEEDED_HEADING = "## Still needed"
SEARCH_MARK = ". Search: "
# app.listing.voice.FIELD as a pack writes it
VOICE_LINE = "  - condition notes: "


def visitor_markdown(markdown: str) -> str:
    """A pack as the demo visitor reads it: the budget line, the condition notes, the searches
    under what is still needed and the outcome section left out, and every private value in
    the rest masked. A value written over several
    lines goes with its first."""
    lines: list[str] = []
    section = ""
    # while a line is being left out, the prefixes of the line that ends it
    skipping: tuple[str, ...] = ()
    for line in markdown.split("\n"):
        if line == OUTCOME_HEADING:
            break
        if line.startswith("## "):
            section, skipping = line, ()
            if lines and lines[-1] != "":
                lines.append("")
        elif skipping:
            if not line.startswith(skipping):
                continue
            skipping = ()
        if line.startswith(BUDGET_LINE):
            continue
        if section == INVENTORY_HEADING and line.startswith(VOICE_LINE):
            skipping = ("- ", "  - ")
            continue
        if section == NEEDED_HEADING and line.startswith("- "):
            cut = line.find(SEARCH_MARK)
            if cut >= 0:
                line = line[:cut]
                skipping = ("- ",)
        lines.append(line)
    # a pack written before private values were masked in it is masked here too
    return mask_text("\n".join(lines).rstrip("\n") + "\n")


class SelectRequest(BaseModel):
    take: bool = Field(
        default=False,
        description="move an item committed to another selected project to this one",
    )


class FillRequest(BaseModel):
    """An item of yours for a requirement the proposal left open: bought since, or overlooked."""

    item_id: int = Field(ge=1)
    why: str = Field(default="", max_length=LINE_MAX)


class Conflict(BaseModel):
    item_id: int
    item_name: str
    project_id: int
    project_title: str

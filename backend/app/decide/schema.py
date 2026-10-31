"""Shapes of the decision: what the model proposes an item is good for, the three scenarios
written for this owner (keep and fix, reuse, sell or give away), what the rules say it fills,
the one view that gathers what is known, and the owner's choice."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.inventory.schema import Intent, ItemSummary
from app.value.schema import Strategy

Effort = Literal["low", "medium", "high"]
# What the owner decides. "Keep and fix" keeps the item as it is, to be repaired; "not worth
# it" keeps it with the note saying why.
Choice = Literal["keep_fix", "keep_build", "sell", "give", "not_worth"]
CHOICES: tuple[Choice, ...] = ("keep_fix", "keep_build", "sell", "give", "not_worth")
INTENT_FOR: dict[str, Intent] = {
    "keep_fix": "keep",
    "keep_build": "build",
    "sell": "sell",
    "give": "give",
    "not_worth": "keep",
}
NOTE_MAX = 200
MAX_USES = 3
MAX_REUSE = 3
# how hard a card is for this owner, by their rated skills
Difficulty = Literal["easy", "moderate", "hard"]
Recommendation = Literal["keep_fix", "reuse", "sell", "give"]


class Use(BaseModel):
    """One thing the item could still be: what it would do, what else it takes, the effort."""

    title: str
    what_it_does: str
    needs: list[str]
    effort: Effort
    note: str


class UsesWriting(BaseModel):
    """Strict output schema of a uses call: every property required, no extras."""

    uses: list[Use]


class KeepFix(BaseModel):
    """The first card: what is likely wrong, how this owner would fix it, and whether to."""

    worth_fixing: bool
    problems: list[str] = Field(description="the likely faults, from what is recorded")
    steps: list[str] = Field(description="the repair, at the owner's level")
    difficulty: Difficulty
    why: str = Field(description="the difficulty for this owner, naming their rated skill")
    parts: list[str] = Field(description="each part with its rough cost")
    cost: str
    time: str


class ReuseScenario(BaseModel):
    """One thing to make of it, with what else the owner already has."""

    title: str
    what_it_does: str
    with_items: list[str] = Field(description="other items of the owner's it would use")
    difficulty: Difficulty
    why: str
    extra_parts: list[str] = Field(description="each part with its rough cost")
    cost: str
    time: str


class SellCard(BaseModel):
    """The third card: what makes it sellable and what selling it takes."""

    selling_points: list[str]
    effort: str = Field(description="what listing and handing it over takes, in a line")
    note: str


class ScenariosWriting(BaseModel):
    """Strict output schema of a scenarios call: every property required, no extras."""

    keep_fix: KeepFix
    reuse: list[ReuseScenario]
    sell: SellCard
    recommended: Recommendation
    reason: str = Field(description="one line, tied to the owner's profile")


class Scenarios(BaseModel):
    """The three cards as kept on the item: written once per asking from one item version."""

    id: int
    item_id: int
    version: int = Field(description="per item; a new request bumps it")
    item_version: int
    stale: bool = Field(
        description="the item changed since the cards were written; a decision is no change"
    )
    steps_in_notes: bool = Field(
        default=False, description="the keep and fix steps of these cards are in the item's notes"
    )
    profiled: bool = Field(description="written for the owner's profile, not an average person")
    keep_fix: KeepFix
    reuse: list[ReuseScenario]
    sell: SellCard
    recommended: Recommendation
    reason: str
    model: str
    from_fixture: bool
    cost_usd: float
    at: str


class TemplateFit(BaseModel):
    """A project template whose requirements this item fills: the rules' answer, no model."""

    id: str
    label: str
    fills: list[str] = Field(description="the requirement keys the item can fill")


class Uses(BaseModel):
    id: int
    item_id: int
    version: int = Field(description="per item; a new request bumps it")
    item_version: int
    stale: bool = Field(description="the item changed since the answer was written")
    templates: list[TemplateFit]
    uses: list[Use] = Field(description="the model's proposals, at most three")
    model: str
    from_fixture: bool
    cost_usd: float
    at: str


class Worth(BaseModel):
    """The latest guidance in one line: the typical figure and the strategy to start from."""

    id: int
    version: int
    currency: str
    typical: float | None = Field(description="asking prices' median, else the estimate's")
    strategy: Strategy | None
    weak: bool
    stale: bool
    at: str


class OpenSearch(BaseModel):
    id: int
    title: str
    status: str
    candidates: int
    handoff_url: str


class Decided(BaseModel):
    """The last decision, read back from the history."""

    choice: Choice
    note: str
    at: str
    version: int


class Decision(BaseModel):
    """One place that walks an item through the decision, from what the app already answers."""

    item: ItemSummary
    accepted_fields: int
    worth: Worth | None
    uses: Uses | None
    scenarios: Scenarios | None
    searches: list[OpenSearch]
    templates: list[TemplateFit]
    intent: Intent
    committed_to: list[str] = Field(
        description="the selected, building or done projects that count on the item, by title"
    )
    last: Decided | None


class DecisionCreate(BaseModel):
    choice: Choice
    note: str = Field(default="", max_length=NOTE_MAX)
    version: int | None = Field(
        default=None, description="the item version the choice was made from; stale is a 409"
    )

    @field_validator("note")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join(value.split())

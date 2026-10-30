"""Shapes of the decision: what the model proposes an item is good for, what the rules say it
fills, the one view that gathers what is known, and the owner's choice."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.inventory.schema import Intent, ItemSummary
from app.value.schema import Strategy

Effort = Literal["low", "medium", "high"]
# What the owner decides. "Not worth it" keeps the item with the note saying why.
Choice = Literal["keep_build", "sell", "give", "not_worth"]
CHOICES: tuple[Choice, ...] = ("keep_build", "sell", "give", "not_worth")
INTENT_FOR: dict[str, Intent] = {
    "keep_build": "build",
    "sell": "sell",
    "give": "give",
    "not_worth": "keep",
}
NOTE_MAX = 200
MAX_USES = 3


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

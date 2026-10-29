"""Shapes of a listing draft: what the model writes, what the rules add, what is stored."""

from pydantic import BaseModel, Field

from app.listing.checklists import Mode, Step


class DraftFact(BaseModel):
    """One line of the draft and the item field or detail it rests on."""

    text: str
    field: str


class DraftWriting(BaseModel):
    """Strict output schema of a draft call: every property required, no extras."""

    title: str
    description: str
    uses: list[str]
    keywords: list[str]
    facts: list[DraftFact]


class DraftRequest(BaseModel):
    mode: Mode = "sell"
    holds_data: bool = Field(default=False, description="the item stores accounts or files")
    pickup: str = ""
    asking_price: str = Field(default="", description="set by the owner; nothing is suggested here")


class Draft(BaseModel):
    id: int
    item_id: int
    mode: Mode
    version: int = Field(description="per item and mode; a new draft bumps it")
    item_version: int = Field(description="the item version the draft was written from")
    stale: bool = Field(description="the item changed since the draft was written")
    title: str
    description: str = Field(description="the model's text with the disclosures the rules add")
    facts: list[DraftFact]
    uses: list[str]
    keywords: list[str]
    warnings: list[str]
    to_confirm: list[str] = Field(
        description="observed fields left out until the owner accepts them"
    )
    pickup: str
    asking_price: str
    holds_data: bool
    checklist: list[Step]
    ready: bool = Field(description="every required step is done")
    handoff_url: str
    model: str
    from_fixture: bool
    cost_usd: float
    at: str


class StepChange(BaseModel):
    key: str
    done: bool

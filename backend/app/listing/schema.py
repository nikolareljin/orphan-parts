"""Shapes of a listing draft: what the model writes, what the rules add, what is stored."""

from pydantic import BaseModel, Field, field_validator

from app.listing.checklists import Mode, Step


class DraftFact(BaseModel):
    """One line of the draft and the item field or detail it rests on."""

    text: str
    field: str


class PhotoPick(BaseModel):
    """One of the item's photos, by its number, and why it sits where it does."""

    photo: int
    reason: str


class DraftWriting(BaseModel):
    """Strict output schema of a draft call: every property required, no extras."""

    title: str
    category: str
    condition: str
    description: str
    uses: list[str]
    tags: list[str]
    facts: list[DraftFact]
    photo_order: list[PhotoPick]


DETAIL_MAX = 200


class DraftRequest(BaseModel):
    mode: Mode = "sell"
    holds_data: bool = Field(default=False, description="the item stores accounts or files")
    pickup: str = Field(default="", max_length=DETAIL_MAX)
    asking_price: str = Field(
        default="",
        max_length=DETAIL_MAX,
        description="set by the owner; the saved listing details are used when this is empty",
    )

    @field_validator("pickup", "asking_price")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join(value.split())


class Draft(BaseModel):
    id: int
    item_id: int
    mode: Mode
    version: int = Field(description="per item and mode; a new draft bumps it")
    item_version: int = Field(description="the item version the draft was written from")
    stale: bool = Field(description="the item changed since the draft was written")
    title: str = Field(description="at most 100 characters")
    price: str = Field(default="", description="whole dollars as typed on Marketplace; 0 is free")
    price_basis: str = Field(default="", description="where the price comes from")
    category: str = Field(default="", description="a path from the Marketplace data file")
    condition: str = Field(default="", description="one of the Marketplace conditions")
    description: str = Field(description="the model's text with the disclosures the rules add")
    facts: list[DraftFact]
    uses: list[str]
    tags: list[str] = Field(default_factory=list, description="at most 20, short")
    photos: list[PhotoPick] = Field(
        default_factory=list, description="the item's photos, best first, with a reason each"
    )
    details_version: int | None = Field(
        default=None, description="the listing details version the draft was written from"
    )
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
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    done: bool

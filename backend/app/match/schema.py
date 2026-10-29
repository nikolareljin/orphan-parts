"""Shapes of an assessment: what is needed, what a candidate shows, and the verdict."""

from typing import Literal

from pydantic import BaseModel, Field

from app.inventory.schema import Provenance, Review
from app.profiles import RuleKind

Status = Literal["pass", "fail", "unknown"]
# The ladder. CONFLICT and EXACT_MATCH are decided by the rules alone; the two in the middle say
# how much of the evidence is there; INSUFFICIENT_INFO is a request for evidence, not a verdict
# on the part.
Verdict = Literal[
    "EXACT_MATCH", "COMPATIBLE_LIKELY", "VISUALLY_SIMILAR", "CONFLICT", "INSUFFICIENT_INFO"
]


class Side(BaseModel):
    """One side of the comparison: an inventory item, or values written in by hand.

    ``values`` are keyed by rule key and written in the candidate's terms: for a vacuum the
    needed ``opening_inner_diameter`` is the wand's outer diameter. A unit in the text is fine
    (``19.5 V``). ``profile`` is taken from an item when it has one."""

    item_id: int | None = None
    values: dict[str, str] = {}
    profile: str = ""


class AssessRequest(BaseModel):
    need: Side
    candidate: Side


class Backing(BaseModel):
    """How the candidate's value is known, when it comes from an inventory item."""

    provenance: Provenance
    review: Review
    source: str
    uncertainty: float | None = Field(default=None, description="in the rule's unit")
    at: str


class Check(BaseModel):
    """One rule applied: the needed value, what the candidate shows, and why it passed or not."""

    key: str
    label: str
    kind: RuleKind
    hard: bool
    identity: bool
    status: Status
    needed: str = Field(description="the required value as given, empty when not given")
    observed: str = Field(description="the candidate's value as known, empty when unknown")
    unit: str
    basis: str
    backing: Backing | None = None


class Assessment(BaseModel):
    profile: str
    verdict: Verdict
    summary: str = Field(description="one line that says what decided the verdict")
    checks: list[Check]
    questions: list[str] = Field(description="what to ask about the candidate's unknowns")
    missing: list[str] = Field(description="rules the need gives no value for")
    to_confirm: list[str] = Field(description="checks resting on an observation not yet accepted")
    need_item: int | None
    candidate_item: int | None

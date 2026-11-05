"""A person's like or dislike of something the app generated, and what one target has."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# what may be voted on, and what its target_id and target_ref name:
#   item_picture     item id, the picture's number                    ("2")
#   card_picture     item id, "<scenarios id>/<card>/<picture number>" ("4/0/1")
#   project_picture  project id, the picture's number
#   scenarios        item id, the set of Decide cards' id
#   uses             item id, the ideas' id
#   draft            draft id
#   price_guidance   item id, the guidance's id
#   search_plan      search id
#   web_find         search id, the listing's id
#   candidate        candidate id
#   project          project id (the proposal)
#   pack             pack id (the build pack)
TargetKind = Literal[
    "item_picture",
    "card_picture",
    "project_picture",
    "scenarios",
    "uses",
    "draft",
    "price_guidance",
    "search_plan",
    "web_find",
    "candidate",
    "project",
    "pack",
]
Vote = Literal["like", "dislike"]

# how many numbers each kind's target_ref holds (0: none)
REF_PARTS: dict[str, int] = {
    "item_picture": 1,
    "card_picture": 3,
    "project_picture": 1,
    "scenarios": 1,
    "uses": 1,
    "draft": 0,
    "price_guidance": 1,
    "search_plan": 0,
    "web_find": 1,
    "candidate": 0,
    "project": 0,
    "pack": 0,
}
PICTURE_KINDS = frozenset({"item_picture", "card_picture", "project_picture"})
REASON_MAX = 200
_NUMBER = r"(0|[1-9][0-9]{0,11})"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def ref_ok(kind: str, ref: str) -> bool:
    """Whether ``ref`` has the shape the kind needs: plain numbers joined by ``/``."""
    parts = REF_PARTS.get(kind)
    if parts is None:
        return False
    if parts == 0:
        return ref == ""
    return re.fullmatch("/".join([_NUMBER] * parts), ref) is not None


class Target(BaseModel):
    target_kind: TargetKind
    target_id: int = Field(ge=1, le=10**12)
    target_ref: str = Field(default="", max_length=40)


class VoteCreate(Target):
    vote: Vote
    reason: str = Field(
        default="",
        max_length=REASON_MAX,
        description="what is wrong (or right) with it, in a line; optional",
    )

    @field_validator("reason")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join(_CONTROL.sub(" ", value).split())


class Tally(Target):
    """What one target has: the votes the caller may count, and the caller's own."""

    likes: int
    dislikes: int
    mine: Vote | None = Field(description="the caller's own vote, if any")
    reason: str = Field(default="", description="the reason the caller gave with it")


class Cast(BaseModel):
    """One vote as kept, for the review tools."""

    target_kind: str
    target_id: int
    target_ref: str
    vote: Vote
    reason: str
    digest: str
    owner_code: int | None
    created_at: str

    @property
    def who(self) -> str:
        return "owner" if self.owner_code is None else f"judge code {self.owner_code}"

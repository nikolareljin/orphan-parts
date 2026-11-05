"""The votes as the review tools read them: for one drawing or one recommendation, how many
people liked or disliked it and why. A dislike is a person flagging it; a like keeps it as an
example of what is right."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field

from app.feedback.schema import Cast

# what --only and --redraw take besides drawing ids: the drawings people voted on
DISLIKED = "disliked"
LIKED = "liked"
PEOPLE_WORDS = (DISLIKED, LIKED)
NO_REASON = "disliked, no reason given"


class People(BaseModel):
    """A person's signal on one drawing or recommendation."""

    likes: int = 0
    dislikes: int = 0
    reasons: list[str] = Field(default=[], description="each dislike's reason, with who gave it")
    stale: int = Field(
        default=0, description="votes on an earlier drawing under the same number, not counted"
    )

    @property
    def disliked(self) -> bool:
        return self.dislikes > 0

    @property
    def liked(self) -> bool:
        """Liked and disliked by nobody: an example to keep as it is."""
        return self.likes > 0 and self.dislikes == 0

    def line(self) -> str:
        said = f"{self.likes} like(s), {self.dislikes} dislike(s)"
        return said + (f" ({self.stale} on an earlier drawing)" if self.stale else "")


def digest_of(path: Path) -> str:
    """The drawing's bytes as a vote keeps them (the API's digest)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def tally(
    votes: Iterable[Cast], kind: str, target_id: int, ref: str = "", file: Path | None = None
) -> People:
    """The votes on one target. With ``file``, a vote cast on other bytes (a drawing redrawn
    under the same number since) is counted as stale, not as a vote on this one."""
    out = People()
    current = digest_of(file) if file is not None else ""
    for v in votes:
        if v.target_kind != kind or v.target_id != target_id or v.target_ref != ref:
            continue
        if file is not None and v.digest and v.digest != current:
            out.stale += 1
            continue
        if v.vote == "like":
            out.likes += 1
        else:
            out.dislikes += 1
            out.reasons.append(f"{v.who}: {v.reason or NO_REASON}")
    return out


def expand(selectors: list[str], people: dict[str, People]) -> list[str]:
    """``disliked`` and ``liked`` among the selectors, as the ids they stand for."""
    out: list[str] = []
    for s in selectors:
        if s == DISLIKED:
            out += sorted(k for k, p in people.items() if p.disliked)
        elif s == LIKED:
            out += sorted(k for k, p in people.items() if p.liked)
        else:
            out.append(s)
    return out

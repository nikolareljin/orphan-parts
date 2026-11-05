"""What a person's votes say to the next drawing of the same thing: the reasons given with a
dislike become what it avoids, the correction a liked drawing was drawn with what it keeps. A
drawing nobody voted on is asked for word for word as before, so its recording still answers.

Each reason is one plain line, private values masked, at most ``REASON_MAX`` characters; the
same reason is said once; the newest come first, at most ``AVOID_MAX`` of the target's own and
``KIND_MAX`` more from other projects of the same kind."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.feedback.schema import REASON_MAX
from app.privacy.text import mask_text

AVOID_MAX = 3
KIND_MAX = 2
KEEP_MAX = 200
# a dislike without a reason still says something: not that one again
NO_REASON = "a different composition than the disliked one"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def clean(text: str, limit: int = REASON_MAX) -> str:
    """One plain line, private values masked, cut to ``limit``."""
    line = " ".join(_CONTROL.sub(" ", text).split())
    return " ".join(mask_text(line).split())[:limit].strip()


@dataclass
class Steer:
    """What the next drawing avoids and keeps; empty when nobody voted."""

    avoid: list[str] = field(default_factory=list)
    keep: str = ""

    def segments(self) -> list[str]:
        """The prompt's added segments, in order; none when there is nothing to say."""
        out = []
        if self.avoid:
            out.append("Avoid: " + "; ".join(self.avoid))
        if self.keep:
            out.append(f"Keep: {self.keep}")
        return out


def _add(into: list[str], text: str, most: int) -> None:
    if len(into) < most and text and text.casefold() not in (x.casefold() for x in into):
        into.append(text)


def assemble(own: Sequence[str], kind: Sequence[str] = (), liked: Sequence[str] = ()) -> Steer:
    """``own``: the reasons of the dislikes of this target, newest first ("" for a dislike
    with none); ``kind``: those of other drawings of the same kind of project, newest first;
    ``liked``: the corrections liked drawings of this target were drawn with, newest first."""
    avoid: list[str] = []
    for reason in own:
        _add(avoid, clean(reason) or NO_REASON, AVOID_MAX)
    extra: list[str] = []
    for reason in kind:
        text = clean(reason)
        if text and text.casefold() not in (x.casefold() for x in avoid):
            _add(extra, text, KIND_MAX)
    keep = next((k for k in (clean(x, KEEP_MAX) for x in liked) if k), "")
    return Steer(avoid=avoid + extra, keep=keep)

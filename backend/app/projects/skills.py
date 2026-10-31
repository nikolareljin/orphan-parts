"""The owner's skills, rated: a fixed starter list every form shows, custom ones beside it, and
one of four levels each. A record kept before the ratings held plain names; those read as
``some``, so nothing the owner wrote is lost."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SkillLevel = Literal["none", "some", "confident", "pro"]
LEVELS: tuple[SkillLevel, ...] = ("none", "some", "confident", "pro")
# the skills every form asks about, in the order shown; custom ones follow
STARTER_SKILLS: tuple[str, ...] = (
    "software",
    "electronics and soldering",
    "woodworking",
    "metalwork",
    "handcrafting and sewing",
    "plumbing",
    "3D printing",
    "arts and crafts",
    "car and mechanics",
    "home repair",
)
SKILL_MAX = 200
# what a plain name is rated when it is read from a record kept before the ratings
MIGRATED_LEVEL: SkillLevel = "some"


class RatedSkill(BaseModel):
    skill: str = Field(min_length=1, max_length=SKILL_MAX)
    level: SkillLevel = MIGRATED_LEVEL

    @field_validator("skill")
    @classmethod
    def _one_line(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("a skill needs a name")
        return value


def rated_skills(values: list[object]) -> list[dict[str, object]]:
    """The list as sent or as stored, in the rated shape: a plain name becomes ``some``, a
    blank name is dropped, and a name given twice keeps its first rating."""
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str):
            entry: dict[str, object] = {"skill": value, "level": MIGRATED_LEVEL}
        elif isinstance(value, dict):
            entry = dict(value)
        elif isinstance(value, RatedSkill):
            entry = value.model_dump()
        else:
            out.append(value)  # type: ignore[arg-type]  # left for the field's own check to refuse
            continue
        name = " ".join(str(entry.get("skill", "")).split())
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        entry["skill"] = name[:SKILL_MAX]
        out.append(entry)
    return out


def skills_line(skills: list[RatedSkill]) -> str:
    """The ratings in one line for a brief: ``software: pro; plumbing: none``."""
    return "; ".join(f"{s.skill}: {s.level}" for s in skills)

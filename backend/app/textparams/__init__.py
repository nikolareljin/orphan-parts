"""The text parameters: what the Decide cards, the ideas and the proposals are told beyond their
fixed instructions, kept as data in ``params.yaml`` beside this file and versioned, as the
drawing parameters are (``app/picture/params.yaml``).

Each section (``scenarios`` for the Decide cards, ``uses`` for the ideas, ``propose`` for the
proposals) can lead the brief with the item's compatibility facts (``facts_first``), and adds
lines after the instructions: ``constraints`` (what every answer must respect),
``corrections`` (what the reviews of the recommendations found, ``./dev decide-review``) and
``banned`` (phrases never to write). An empty section adds nothing, so its requests are word for
word what they were and their recordings still answer. ``./dev decide-review --tune`` proposes
edits from the last review, ``--tune --apply`` writes them and bumps ``version``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

TEXT_PARAMS_FILE = Path(__file__).with_name("params.yaml")
LINE_MAX = 300
LINES_MAX = 12
Section = Literal["scenarios", "uses", "propose"]
SECTIONS: tuple[Section, ...] = ("scenarios", "uses", "propose")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        line = " ".join(str(v).split())
        if line and line not in out:
            out.append(line)
    return out


class TextSection(_Strict):
    """What one kind of request adds to its instructions and its brief."""

    facts_first: bool = Field(
        default=False,
        description="the brief opens with the item's compatibility facts (memory, socket, size)",
    )
    constraints: list[str] = Field(default=[], description="rules every answer respects")
    corrections: list[str] = Field(default=[], description="learned from the reviews")
    banned: list[str] = Field(default=[], description="phrases never written")

    @field_validator("constraints", "corrections", "banned")
    @classmethod
    def _lines(cls, value: list[str]) -> list[str]:
        cleaned = _clean(value)
        if len(cleaned) > LINES_MAX:
            raise ValueError(f"at most {LINES_MAX} lines")
        for line in cleaned:
            if len(line) > LINE_MAX:
                raise ValueError(f"a line of at most {LINE_MAX} characters: {line[:40]}...")
        return cleaned

    def instructions(self, base: str) -> str:
        """The fixed instructions, then this section's lines; nothing added when it is empty."""
        extra: list[str] = []
        if self.constraints:
            extra.append("Also: " + " ".join(_sentence(c) for c in self.constraints))
        if self.corrections:
            extra.append(
                "Mistakes to avoid, found in earlier answers: "
                + " ".join(_sentence(c) for c in self.corrections)
            )
        if self.banned:
            extra.append(
                "Never write these phrases or their like: "
                + "; ".join(f'"{b}"' for b in self.banned)
                + "."
            )
        return base + "".join(f" {e}" for e in extra)


def _sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


class TextParams(_Strict):
    version: int = Field(ge=1)
    scenarios: TextSection = TextSection()
    uses: TextSection = TextSection()
    propose: TextSection = TextSection()

    def section(self, name: Section) -> TextSection:
        section: TextSection = getattr(self, name)
        return section


def parse(raw: Any) -> TextParams:
    if not isinstance(raw, dict):
        raise ValueError("the text parameters are a mapping")
    return TextParams.model_validate(raw)


def load(path: Path | None = None) -> TextParams:
    """The file as it is now: read on each request, so a change takes effect at once."""
    target = path or TEXT_PARAMS_FILE
    try:
        return parse(yaml.safe_load(target.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f"{target.name}: {exc}") from exc


def dump(params: TextParams, path: Path | None = None) -> None:
    """The file written whole, its header comment kept."""
    target = path or TEXT_PARAMS_FILE
    head: list[str] = []
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            if not line.startswith("#"):
                break
            head.append(line)
    body = yaml.safe_dump(
        params.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
    )
    text = ("\n".join(head) + "\n\n" if head else "") + body
    partial = target.with_suffix(".yaml.part")
    partial.write_text(text, encoding="utf-8")
    partial.replace(target)


def attrs_line(attrs: dict[str, Any]) -> str:
    """An item's compatibility facts as the rules read them, one line: ``socket LGA1155;
    memory DDR3``."""
    said: list[str] = []
    for key, value in attrs.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list | tuple | set):
            value = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            continue
        said.append(f"{key.replace('_', ' ')} {value}")
    return "; ".join(said)

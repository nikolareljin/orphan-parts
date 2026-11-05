"""The drawing parameters: what every Muse Image request is built from, kept as data in
``params.yaml`` beside this file and versioned.

A request is said in this order: what is drawn and the parts it is built from, each with its
facts (sizes first); what it does and how it is shown; the correction its kind of project
carries; the drawing's own brief (from a review, kept in the demo set); the negatives; then the
closing rules for its kind of drawing. ``./dev picture-review --tune`` proposes changes to the
file from the reviews, ``--tune --apply`` writes them and bumps ``version``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PARAMS_FILE = Path(__file__).with_name("params.yaml")
TEXT_MAX = 400
LOOKS_MAX = 200
NEGATIVE_MAX = 200
RULE_MAX = 200

# a size in the owner's name for an item: "18 inch", "2.5 inch", "480 GB", "450 W"; nothing
# else of the name is ever said
NAME_SIZE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(inch(?:es)?|\"|cm|mm|GB|TB|W)(?!\w)", re.I)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _words(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        word = " ".join(str(v).split()).lower()
        if word and word not in out:
            out.append(word)
    return out


class FactRules(_Strict):
    """Which accepted values of a part are said, in what order, and how many."""

    item_values: int = Field(default=8, ge=0, le=20, description="values of an item's own picture")
    part_values: int = Field(default=3, ge=0, le=20, description="values of each part of a build")
    first: list[str] = Field(default=[], description="field-name words said before the rest")
    left_out: list[str] = Field(default=[], description="field-name words never said")
    left_out_as_built: list[str] = Field(
        default=["condition", "certification"],
        description="also never said of a part of a finished project",
    )
    from_name: bool = Field(default=False, description="sizes read from the owner's name")
    condition: bool = Field(default=True, description="an item's picture says its condition")

    @field_validator("first", "left_out", "left_out_as_built")
    @classmethod
    def _norm(cls, value: list[str]) -> list[str]:
        return _words(value)


class KindLook(_Strict):
    """A kind of part (an item type, lower case): how it looks at its real size."""

    looks: str = Field(default="", max_length=LOOKS_MAX)
    size: str = Field(default="size", max_length=40, description="what its name's size is called")
    built: str = Field(
        default="",
        max_length=LOOKS_MAX,
        description="how it is said as a part of a finished project, instead of looks",
    )


class ProjectCorrection(_Strict):
    """A kind of project (a template id): what its drawings must and must not show."""

    match: list[str] = Field(default=[], description="words in a use or a card title meaning it")
    correction: str = Field(default="", max_length=TEXT_MAX)
    built: str = Field(
        default="",
        max_length=TEXT_MAX,
        description="the correction of a finished project of this template, instead of correction",
    )

    @field_validator("match")
    @classmethod
    def _norm(cls, value: list[str]) -> list[str]:
        return _words(value)


class ClosingRules(_Strict):
    """The closing words of each kind of drawing."""

    item: str = Field(max_length=RULE_MAX, description="an item drawn as itself")
    use: str = Field(max_length=RULE_MAX, description="an item drawn as a use")
    card: str = Field(max_length=RULE_MAX, description="a reuse card's project")
    project: str = Field(max_length=RULE_MAX, description="a finished project")


class DrawingParams(_Strict):
    version: int = Field(ge=1)
    facts: FactRules = FactRules()
    kinds: dict[str, KindLook] = {}
    projects: dict[str, ProjectCorrection] = {}
    views: dict[str, str] = Field(default={}, description="words in a view and what to add")
    negatives: list[str] = []
    rules: ClosingRules

    @field_validator("kinds", "projects", "views")
    @classmethod
    def _lower_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {" ".join(str(k).split()).lower(): v for k, v in value.items()}

    @field_validator("views")
    @classmethod
    def _view_bounds(cls, value: dict[str, str]) -> dict[str, str]:
        for k, v in value.items():
            if len(v) > TEXT_MAX:
                raise ValueError(f"view {k!r}: at most {TEXT_MAX} characters")
        return value

    @field_validator("negatives")
    @classmethod
    def _negative_bounds(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for v in value:
            text = " ".join(v.split())
            if len(text) > NEGATIVE_MAX:
                raise ValueError(f"a negative is at most {NEGATIVE_MAX} characters: {text[:40]}")
            if text and text.casefold() not in (o.casefold() for o in out):
                out.append(text)
        return out

    # --- what the prompt builder asks of it ---------------------------------------------------

    def kind(self, item_type: str) -> KindLook | None:
        return self.kinds.get(" ".join(item_type.split()).lower())

    def correction_for(self, template: str = "", text: str = "") -> str:
        """The correction of a project's template, else of the first kind of project whose
        words the use or the title says."""
        found = self.projects.get(template.lower()) if template else None
        if found is not None:
            return found.built or found.correction
        said = " ".join(text.split()).lower()
        if not said:
            return ""
        for p in self.projects.values():
            if p.correction and any(word in said for word in p.match):
                return p.correction
        return ""

    def view_preset(self, view: str) -> str:
        said = " ".join(view.split()).lower()
        for words, preset in self.views.items():
            if words and words in said:
                return preset
        return ""


class ParamsError(ValueError):
    """The parameters file does not read as drawing parameters."""


def parse(text: str, where: str = "params") -> DrawingParams:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ParamsError(f"{where}: not YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise ParamsError(f"{where}: a map of drawing parameters")
    try:
        return DrawingParams.model_validate(raw)
    except ValidationError as exc:
        raise ParamsError(f"{where}: {exc}") from exc


_cache: dict[Path, tuple[float, DrawingParams]] = {}


def load(path: Path | None = None) -> DrawingParams:
    """The parameters as the file says now; read again when it changes."""
    target = path or PARAMS_FILE
    stamp = target.stat().st_mtime
    hit = _cache.get(target)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    params = parse(target.read_text(encoding="utf-8"), str(target))
    _cache[target] = (stamp, params)
    return params


def name_sizes(name: str, item_type: str, params: DrawingParams) -> list[str]:
    """The sizes the owner's name for an item states, said as facts (``screen size 18 inch,
    about 46 cm across the diagonal``); never another word of the name."""
    if not params.facts.from_name:
        return []
    kind = params.kind(item_type)
    label = kind.size if kind is not None else "size"
    out: list[str] = []
    for number, unit in NAME_SIZE.findall(name or ""):
        unit_said = "inch" if unit.lower().startswith("inch") or unit == '"' else unit
        fact = f"{label} {number} {unit_said}"
        if unit_said == "inch" and "screen" in label:
            fact += f", about {round(float(number) * 2.54)} cm across the diagonal"
        if fact not in out:
            out.append(fact)
    return out


# --- the file, written back ----------------------------------------------------------------

HEADER = """\
# The drawing parameters: what every Muse Image request of Orphan Parts Lens is built from.
# Read by backend/app/picture/service.py on each drawing (a change takes effect at once) and
# written by `./dev picture-review --tune --apply`, which bumps `version`; the evaluation of
# each version is kept in eval/pictures/params-v<version>.json. The guide is
# docs/guides/picture-review.md#tuning-the-drawing-parameters.
#
# A request says, in order: what is drawn and its parts, each with its facts (sizes first);
# what it does and how it is shown (a view adds its preset); the correction of its kind of
# project; the drawing's own brief from the demo set; the negatives; the closing rules.
# A change here changes the requests, so every drawing of the demo set is drawn and recorded
# again (`./dev picture-review --redraw-set`).
"""

SECTIONS = {
    "version": "",
    "facts": (
        "# which accepted values of a part are said: those whose name has a `first` word go\n"
        "# first, none whose name has a `left_out` word (prices never), at most `item_values`\n"
        "# for an item's own picture and `part_values` for a part of a build; `from_name` adds\n"
        "# the sizes the owner's name states (18 inch, 480 GB), nothing else of it;\n"
        "# `condition` says an item's condition and faults in its own picture"
    ),
    "kinds": (
        "# by item type: how the part looks at its real size, and what a size in its name is\n"
        "# called (a monitor's is its screen size); `built`: how it is said as a part of a\n"
        "# finished project instead (any computer may be taken apart and its parts built in)"
    ),
    "projects": (
        "# by project template id: the correction every drawing of that kind of project carries;\n"
        "# `match`: words in an item's use or a reuse card's title that mean it; `built`: the\n"
        "# correction of a finished project of the template instead (items and cards keep theirs)"
    ),
    "views": "# words in a view (as the demo set or the app asks it) and what it adds",
    "negatives": "# said after the brief in every request",
    "rules": "# the closing words of each kind of drawing",
}


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_Dumper.add_representer(str, _str)


def dump(params: DrawingParams) -> str:
    """The file's text: the header, then each section under its comment."""
    data = params.model_dump(mode="json")
    parts = [HEADER]
    for key, comment in SECTIONS.items():
        block = yaml.dump(
            {key: data[key]},
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            width=96,
            default_flow_style=False,
        )
        parts.append((comment + "\n" if comment else "") + block)
    return "\n".join(parts)


def save(params: DrawingParams, path: Path | None = None) -> Path:
    target = path or PARAMS_FILE
    text = dump(params)
    parse(text, str(target))
    partial = target.with_name(f".{target.name}.part")
    partial.write_text(text, encoding="utf-8")
    partial.replace(target)
    return target

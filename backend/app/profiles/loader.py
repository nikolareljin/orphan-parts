"""Profiles are YAML files under ``app/profiles/data``. The model never changes them."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

DATA_DIR = Path(__file__).parent / "data"
KEY = r"^[a-z][a-z0-9_]{0,63}$"

# How a rule compares the candidate's value with the needed one.
RuleKind = Literal["equal", "within", "at_least", "at_most"]


class Feature(BaseModel):
    """One dimension worth measuring, with the tolerance a match may allow."""

    key: str = Field(pattern=KEY)
    label: str
    unit: str = "mm"
    tolerance_mm: float = Field(gt=0)
    how: str


class Rule(BaseModel):
    """One requirement a candidate is checked against: pass, fail or unknown, never a guess.

    A ``hard`` rule decides the verdict; a soft one is reported. An ``identity`` rule (part or
    model number) that passes makes the match exact. A numeric rule allows ``tolerance`` in the
    unit, ``tolerance_pct`` of the needed value, or both (the larger wins); a rule whose key is
    also a feature takes the feature's tolerance when it names none. ``question`` is what to ask
    the seller when the candidate's value is unknown."""

    key: str = Field(pattern=KEY)
    label: str
    kind: RuleKind
    unit: str = ""
    hard: bool = True
    identity: bool = False
    tolerance: float | None = Field(default=None, ge=0)
    tolerance_pct: float | None = Field(default=None, ge=0)
    question: str = ""


class ProfileSummary(BaseModel):
    id: str
    label: str
    feature_count: int
    rule_count: int


class Profile(BaseModel):
    id: str = Field(pattern=KEY)
    label: str
    description: str = ""
    features: list[Feature] = []
    rules: list[Rule] = []

    @model_validator(mode="after")
    def _consistent(self) -> "Profile":
        feature_by_key = {f.key: f for f in self.features}
        if len(feature_by_key) != len(self.features):
            raise ValueError(f"profile {self.id!r} repeats a feature key")
        seen: set[str] = set()
        for rule in self.rules:
            if rule.key in seen:
                raise ValueError(f"profile {self.id!r} repeats rule {rule.key!r}")
            seen.add(rule.key)
            feature = feature_by_key.get(rule.key)
            if feature is not None:
                if rule.tolerance is None and rule.tolerance_pct is None:
                    rule.tolerance = feature.tolerance_mm
                if not rule.unit:
                    rule.unit = feature.unit
            if rule.kind == "within" and rule.tolerance is None and rule.tolerance_pct is None:
                raise ValueError(f"rule {rule.key!r} of {self.id!r}: within needs a tolerance")
            if rule.kind == "equal" and (
                rule.tolerance is not None or rule.tolerance_pct is not None
            ):
                raise ValueError(f"rule {rule.key!r} of {self.id!r}: equal takes no tolerance")
        return self


class UnknownProfileError(LookupError):
    pass


class Profiles:
    """Every profile file, loaded once at startup and validated."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self._by_id: dict[str, Profile] = {}
        for path in sorted(data_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
            profile = Profile.model_validate(raw)
            if profile.id != path.stem:
                raise ValueError(
                    f"{path.name} declares id {profile.id!r}; the file name must match"
                )
            self._by_id[profile.id] = profile

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def summaries(self) -> list[ProfileSummary]:
        return [
            ProfileSummary(
                id=p.id, label=p.label, feature_count=len(p.features), rule_count=len(p.rules)
            )
            for p in (self._by_id[i] for i in self.ids())
        ]

    def get(self, profile_id: str) -> Profile:
        try:
            return self._by_id[profile_id]
        except KeyError as exc:
            raise UnknownProfileError(f"no profile {profile_id!r}") from exc

    def feature(self, profile_id: str | None, key: str) -> Feature | None:
        """The feature behind a key, when the profile names it."""
        if not profile_id:
            return None
        return next((f for f in self.get(profile_id).features if f.key == key), None)

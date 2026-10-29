"""Profiles are YAML files under ``app/profiles/data``. The model never changes them."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent / "data"


class Feature(BaseModel):
    """One dimension worth measuring, with the tolerance a match may allow."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str
    unit: str = "mm"
    tolerance_mm: float = Field(gt=0)
    how: str


class ProfileSummary(BaseModel):
    id: str
    label: str
    feature_count: int


class Profile(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str
    description: str = ""
    features: list[Feature] = []


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
            ProfileSummary(id=p.id, label=p.label, feature_count=len(p.features))
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

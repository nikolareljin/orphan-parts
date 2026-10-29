from fastapi import APIRouter, HTTPException

from app.api.deps import ProfilesDep
from app.profiles import Feature, Profile, ProfileSummary, UnknownProfileError

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileSummary])
def list_profiles(profiles: ProfilesDep) -> list[ProfileSummary]:
    """Every category profile shipped as data."""
    return profiles.summaries()


@router.get("/{profile_id}", response_model=Profile)
def get_profile(profile_id: str, profiles: ProfilesDep) -> Profile:
    try:
        return profiles.get(profile_id)
    except UnknownProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{profile_id}/features", response_model=list[Feature])
def profile_features(profile_id: str, profiles: ProfilesDep) -> list[Feature]:
    """The dimensions worth measuring for this kind of item, with their tolerances."""
    try:
        return profiles.get(profile_id).features
    except UnknownProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

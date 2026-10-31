"""Facebook Marketplace (US) as data: the categories and conditions a draft may name, the
checks that keep contact details and street addresses out of a listing, and the photo zip.

Nothing here talks to Facebook. No public API posts a personal Marketplace listing and
automating the site is against its terms, so the app prepares the fields and opens the create
page; the owner pastes them and posts."""

import re
import zipfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import yaml
from pydantic import BaseModel

DATA_FILE = Path(__file__).parent / "marketplace_us.yaml"
TITLE_MAX = 100
TAGS_MAX = 20
TAG_MAX = 30

# A street address: a house number, a capitalized street name and a street word ("12 Oak St",
# "450 W Elm Avenue"), or a unit ("Apt 4B"). Capitals keep "1 TB drive" and "2 way" out of it.
_STREET = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z][a-z'.-]+\s+){1,4}"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Pl|Place|Way"
    r"|Ter|Terrace|Pkwy|Parkway|Hwy|Highway|Cir|Circle)\b\.?"
    r"|\b(?:Apt|Apartment|Unit|Suite|Ste|apt|apartment|suite)\.?\s*#?\s*\d+\w*"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# ten digits in the usual US groupings, with or without +1
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")


class Category(BaseModel):
    path: str
    seen: bool
    holds: str = ""


class MarketplaceData(BaseModel):
    categories: list[Category]
    conditions: list[str]
    free_category: str


@lru_cache(maxsize=1)
def data(path: Path = DATA_FILE) -> MarketplaceData:
    """The data file, flattened to "Top" and "Top > Sub" paths, in the file's order."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    flat: list[Category] = []
    for top in raw["categories"]:
        flat.append(Category(path=top["name"], seen=bool(top.get("seen")), holds=""))
        for sub in top.get("subcategories") or []:
            flat.append(
                Category(
                    path=f"{top['name']} > {sub['name']}",
                    seen=bool(sub.get("seen")),
                    holds=str(sub.get("holds") or ""),
                )
            )
    found = {c.path for c in flat}
    if raw["free_category"] not in found:
        raise ValueError(f"{path}: free_category {raw['free_category']!r} is not a category")
    return MarketplaceData(
        categories=flat, conditions=list(raw["conditions"]), free_category=raw["free_category"]
    )


def category_paths() -> list[str]:
    return [c.path for c in data().categories]


def pick_category(said: str) -> str:
    """The path the draft named when it is in the file, case and spacing aside; else the top
    category it starts with; else empty, for the owner to choose."""
    wanted = " > ".join(p.strip() for p in said.split(">")).casefold()
    by_fold = {p.casefold(): p for p in category_paths()}
    if wanted in by_fold:
        return by_fold[wanted]
    top = wanted.split(" > ")[0]
    return by_fold.get(top, "")


def pick_condition(said: str) -> str:
    by_fold = {c.casefold().replace(" ", ""): c for c in data().conditions}
    return by_fold.get(said.casefold().replace(" ", ""), "")


def personal_details(text: str) -> list[str]:
    """What in the text reads as a street address, an email address or a phone number."""
    found = []
    if _STREET.search(text):
        found.append("a street address")
    if _EMAIL.search(text):
        found.append("an email address")
    if _PHONE.search(text):
        found.append("a phone number")
    return found


def strip_personal(text: str) -> tuple[str, list[str]]:
    """The text with addresses, emails and phone numbers taken out, and what was taken."""
    found = personal_details(text)
    for pattern in (_EMAIL, _PHONE, _STREET):
        text = pattern.sub("[removed]", text)
    return text, found


def photo_zip(photos: list[tuple[int, bytes]]) -> bytes:
    """The chosen photos in order, as stored (re-encoded on the way in, metadata dropped).
    Entries carry a fixed date, so the archive says nothing about when it was made."""
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
        for place, (n, jpeg) in enumerate(photos, 1):
            info = zipfile.ZipInfo(f"{place:02d}-photo-{n}.jpg", date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(info, jpeg)
    return out.getvalue()

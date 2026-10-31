"""The device a part came from. A part that carries no model number of its own (an agitator,
a vacuum tool) is tied to a device by the device it came off; the rule here says when the app
should ask for it, the same answer for the web page and the phone."""

from collections.abc import Mapping
from functools import lru_cache

from app.extract.schema import Extraction
from app.inventory.schema import Assertion
from app.profiles import Profile, Profiles, UnknownProfileError

# the owner's words about the device ("the Oster frappé maker from the kitchen"): kept like the
# notes, never shown to the demo visitor nor sent to a brief other than the owner's own search
PARENT_DEVICE = "parent_device"
# the device's model as read off a photo of its label, or typed: product data, not private
PARENT_MODEL = "parent_device_model"
PARENT_FIELDS = (PARENT_DEVICE, PARENT_MODEL)


@lru_cache(maxsize=1)
def default_profiles() -> Profiles:
    """The profiles shipped with the app, loaded once: they are files, never changed at run."""
    return Profiles()


def profile_of(profile_id: str) -> Profile | None:
    if not profile_id:
        return None
    try:
        return default_profiles().get(profile_id)
    except UnknownProfileError:
        return None


def _stated(fields: Mapping[str, Assertion], key: str) -> bool:
    a = fields.get(key)
    return a is not None and a.review != "rejected" and bool(a.value.strip())


def needs_parent(
    fields: Mapping[str, Assertion], parent_id: int | None, profile: Profile | None
) -> bool:
    """Whether to ask which device the part came from: a part profile, no model or part number
    of its own (an identity rule's field), no parent record and no parent device given."""
    if profile is None or not profile.part_of_device or parent_id is not None:
        return False
    if any(_stated(fields, k) for k in PARENT_FIELDS):
        return False
    return not any(_stated(fields, r.key) for r in profile.rules if r.identity)


def device_model(reading: Extraction) -> tuple[str, float, str]:
    """The device's model from a label reading: the brand and the model number (the part number
    when there is no model number), with the lower confidence and the text as printed."""
    code = reading.fields.get("model_number") or reading.fields.get("part_number")
    if code is None or not code.value.strip():
        return "", 0.0, ""
    brand = reading.fields.get("brand")
    if brand is None or not brand.value.strip():
        return code.value.strip(), code.confidence, code.raw
    value = f"{brand.value.strip()} {code.value.strip()}"
    confidence = min(code.confidence, brand.confidence)
    raw = " ".join(p for p in (brand.raw, code.raw) if p)
    return value, confidence, raw

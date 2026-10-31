"""The steps before an item changes hands, as data. The owner ticks them; nothing is assumed."""

from typing import Literal

from pydantic import BaseModel

Mode = Literal["sell", "give"]
Group = Literal["prepare", "photos", "data"]


class Step(BaseModel):
    key: str
    label: str
    group: Group
    required: bool
    done: bool = False


_PREPARE: list[tuple[str, str, bool]] = [
    ("clean", "Clean the outside with what the surface allows; nothing invasive", True),
    ("test", "Test what the draft will claim, and only that", True),
    ("accessories", "Gather every accessory, cable and part that goes with it", True),
    ("faults", "Write down every fault and mark you know of", True),
    ("pickup", "Decide the pickup area and how it is handed over", True),
    (
        "allowed",
        "Check Marketplace allows it (Meta's Commerce Policies): not recalled, not a medical"
        " device, nothing that unlocks paid streaming or services",
        True,
    ),
]
_PHOTOS: list[tuple[str, str, bool]] = [
    ("photo_front", "Front, in daylight, on a plain background", True),
    ("photo_back", "Back and sides", True),
    ("photo_label", "The label, sharp and readable", True),
    (
        "photo_identifiers",
        "Cover the serial number, MAC or IMEI on the label photo before posting",
        True,
    ),
    ("photo_faults", "Every fault, close up, nothing hidden by the crop", True),
    ("photo_included", "Everything included, laid out together", False),
]
_DATA: list[tuple[str, str, bool]] = [
    ("sign_out", "Sign out of every account and remove the device from them", True),
    ("reset", "Factory reset, or wipe the storage", True),
    ("media", "Take out cards, SIMs and drives, or wipe them", True),
    ("limits", "Note what could not be done (a locked device, a drive that will not wipe)", True),
]


def checklist(mode: Mode, holds_data: bool) -> list[Step]:
    """The steps for this handover. Data removal applies only to things that store data."""
    steps = [Step(key=k, label=label, group="prepare", required=r) for k, label, r in _PREPARE]
    if mode == "give":
        steps = [s for s in steps if s.key != "test"] + [
            Step(
                key="test",
                label="Say what was tested and what was not",
                group="prepare",
                required=True,
            )
        ]
    steps += [Step(key=k, label=label, group="photos", required=r) for k, label, r in _PHOTOS]
    if holds_data:
        steps += [Step(key=k, label=label, group="data", required=r) for k, label, r in _DATA]
    return steps


def ready(steps: list[Step]) -> bool:
    return all(s.done for s in steps if s.required)

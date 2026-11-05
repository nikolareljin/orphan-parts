"""The reuse policy: mains-powered items always carry a safety note, and a use that asks
for circumvention is refused, whatever the model wrote."""

import pytest

from app.decide.policy import MAINS_NOTE, mains_powered, refused_use, safety_for


@pytest.mark.parametrize(
    ("known", "mains"),
    [
        ({"input_voltage": "100-240 V"}, True),
        ({"input_voltage": "230"}, True),
        ({"input_voltage": "120 V"}, True),
        ({"input_voltage": "19.5 V"}, False),
        ({"input_voltage": "12 V"}, False),
        ({"output_voltage": "230 V"}, False),
        ({}, False),
    ],
)
def test_mains_powered_reads_the_input_voltage(known: dict[str, str], mains: bool) -> None:
    assert mains_powered(known) is mains


def test_safety_for_is_the_mains_note_or_nothing() -> None:
    assert safety_for({"input_voltage": "100-240 V"}) == [MAINS_NOTE]
    assert safety_for({"input_voltage": "19.5 V"}) == []
    assert len(MAINS_NOTE) <= 200


@pytest.mark.parametrize(
    "title",
    [
        "Jailbreak the tablet for emulators",
        "Bypass the meter to run it free",
        "Bypass DRM on your ebooks",
        "Strip the DRM from the firmware",
        "Root the phone for a kiosk",
        "Unlock the carrier lock",
        "Unlock the phone for any SIM",
        "Unlock your iPhone for another carrier",
        "carrier unlock service",
        "SIM unlock the handset",
        "Network unlocking for the old phone",
        "iCloud unlock",
        "Remove the iCloud lock",
        "iCloud lock removal",
        "Bypass iCloud activation",
        "Remove the activation lock",
        "Remove the carrier lock",
        "Bypass Google FRP",
        "Play pirated ROMs on it",
        "Read up on software piracy",
    ],
)
def test_circumvention_uses_are_refused(title: str) -> None:
    assert refused_use(title, "saves money") is True
    assert refused_use("Media player", title.lower()) is True


@pytest.mark.parametrize(
    "title",
    [
        "Add a bypass capacitor to the radio",
        "Find the root cause of the hum",
        "Unlock the door with a smart button",
        "carrier-unlocked phone as music player",
        "Remove iCloud photos from the old phone",
        "Sign out of the iCloud account",
        "Remove the door lock, keep the motor",
        "Remove the lock nut and reuse the motor",
        "Remove the lock screen and run it as a kiosk",
        "Unlock the phone to see the doorbell feed",
        "Tap to unlock the phone and open the app",
        "Unlock the full potential of the old phone",
        "Phone stand from the hinge",
        "iCloud photos backup station",
        "Carrier board for the compute module",
        "Battery carrier; unlock it with the latch",
        "Pirate-themed case mod",
        "Music player for the kitchen",
    ],
)
def test_ordinary_uses_are_kept(title: str) -> None:
    assert refused_use(title, "an afternoon project") is False

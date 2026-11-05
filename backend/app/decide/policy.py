"""The reuse policy, enforced deterministically: the instructions ask the model to stay
inside it, what is guaranteed sits here, on every answer no matter what was written."""

import re

from app.match.rules import number

# a mains input starts here: below it a device runs off a brick or a battery
MAINS_VOLTS = 90.0

MAINS_NOTE = "Mains-powered: unplug it before you open it, and keep it away from water."

# a use whose title or text matches one of these asks for circumvention: bypassing locks,
# meters, DRM or carriers. A backstop, deliberately narrow: "bypass capacitor" or "root
# cause" must never match, so every pattern names its object.
_CIRCUMVENTION = (
    ("jailbreak", re.compile(r"\bjailbreak\w*\b", re.IGNORECASE)),
    (
        "bypass",
        re.compile(
            r"\bbypass\w*\s+(the\s+)?(drm|lock|meter|safety|paywall|activation|password)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "drm",
        re.compile(
            r"\b(remov\w*|strip\w*|crack\w*)\b.{0,24}\bdrm\b"
            r"|\bdrm\b.{0,24}\b(remov\w*|strip\w*|bypass\w*|crack\w*)\b",
            re.IGNORECASE,
        ),
    ),
    ("root", re.compile(r"\broot\w*\b.{0,24}\b(phone|tablet|device)\b", re.IGNORECASE)),
    ("unlock", re.compile(r"\bunlock\w*\b.{0,24}\b(carrier|bootloader)\b", re.IGNORECASE)),
    # a phone freed from its carrier: named by the carrier, SIM or network, never by "unlock
    # the phone" alone, which is also how a screen is woken ("unlock the phone to see the feed")
    (
        "sim_unlock",
        re.compile(
            r"\b(carrier|sim|network)[\s-]*unlock(ing|s)?\b"
            r"|\bunlock(ing)?\b.{0,24}\b(for|to|on|with)\s+(any|another|other|a\s+different)"
            r"\s+(carrier|sim|network)s?\b",
            re.IGNORECASE,
        ),
    ),
    # a lock asked off that ties the device to an owner or a carrier; a door lock, a lock nut
    # or a lock screen is not one of them
    (
        "lock_removal",
        re.compile(
            r"\b(remov\w*|bypass\w*|break\w*|disabl\w*)\b.{0,24}"
            r"\b(carrier|sim|network|activation|frp|icloud)[\s-]+lock\b"
            r"|\b(carrier|sim|network|activation|frp|icloud)[\s-]+lock\b.{0,24}"
            r"\b(remov\w*|bypass\w*)\b"
            r"|\b(bypass\w*|remov\w*)\b.{0,24}\bfrp\b|\bfrp\b.{0,24}\b(bypass\w*|remov\w*)\b",
            re.IGNORECASE,
        ),
    ),
    # iCloud unlocked or bypassed, not an account signed out or photos backed up
    (
        "icloud",
        re.compile(
            r"\bicloud\b.{0,12}\b(unlock\w*|bypass\w*)\b"
            r"|\b(unlock\w*|bypass\w*)\b.{0,12}\bicloud\b",
            re.IGNORECASE,
        ),
    ),
    ("piracy", re.compile(r"\bpirat(ed|ing)\b|\bpiracy\b", re.IGNORECASE)),
)


def mains_powered(known: dict[str, str]) -> bool:
    """Whether the item's mains input reads mains voltage: the facts say so, not the model."""
    volts = known.get("input_voltage")
    return volts is not None and (number(volts) or 0.0) >= MAINS_VOLTS


def safety_for(known: dict[str, str]) -> list[str]:
    """The safety notes an answer about these facts must carry, whatever it proposes."""
    return [MAINS_NOTE] if mains_powered(known) else []


def refused_use(title: str, what_it_does: str) -> bool:
    """Whether a use asks for circumvention: bypassing locks, meters, DRM or carriers."""
    text = f"{title}\n{what_it_does}"
    return any(match.search(text) is not None for _, match in _CIRCUMVENTION)

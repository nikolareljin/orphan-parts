"""Private details in text, found by rules alone (no model): product keys, MAC addresses,
IMEIs, serial numbers and passwords, PINs and Wi-Fi keys as a label or a note writes them.
Text that leaves the owner's view is masked with what is found here: the value hidden, its
last four characters kept where that is safe, the words around it left as they are."""

import re
from dataclasses import dataclass
from typing import Literal

from app.ops.door import PRIVATE_FIELDS

# What a private detail is, in text and on a photo. The photo check adds QR codes, barcodes
# and anything else private it sees (an account number, a network name beside its key).
Kind = Literal[
    "product_key",
    "mac_address",
    "serial_number",
    "imei",
    "password",
    "qr_code",
    "barcode",
    "other",
]
KIND_LABELS: dict[str, str] = {
    "product_key": "product key",
    "mac_address": "MAC address",
    "serial_number": "serial number",
    "imei": "IMEI",
    "password": "password or PIN",
    "qr_code": "QR code",
    "barcode": "barcode",
    "other": "private detail",
}
DOT = "•"
HIDDEN = DOT * 4
# a value at least this long keeps its last four characters ("•••• 7QX9"); a shorter one,
# and any password, keeps nothing
KEEP_TAIL_FROM = 10

# Field names that identify the item or its owner: as whole words of the key (``mac`` keeps
# ``mac`` and ``mac_address`` out, not ``machine``), and a few as any part of it.
PRIVATE_WORDS = frozenset(
    {
        "serial",
        "sn",
        "imei",
        "mac",
        "vin",
        "account",
        "password",
        "pin",
        "location",
        "address",
        "phone",
        "email",
        "owner",
        "plate",
        "licence",
        "license",
        "ssn",
        "iban",
        "imsi",
        "iccid",
        "meid",
    }
)
PRIVATE_PARTS = ("serial", "password", "passwd", "service_tag", "servicetag", "product_key")


def private_field(key: str) -> bool:
    """A field that identifies the item or its owner, or is the owner's own words (the device a
    part came from, as they described it): kept out of every brief and document."""
    if key.lower() in PRIVATE_FIELDS:
        return True
    words = key.lower().split("_")
    return any(w in PRIVATE_WORDS for w in words) or any(p in key.lower() for p in PRIVATE_PARTS)


# Five groups of five letters and digits, as Windows and Office print them.
_PRODUCT_KEY = re.compile(r"(?<![A-Z0-9-])[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}(?![A-Z0-9-])", re.I)
# Six hex pairs joined by one separator throughout, or three groups of four joined by dots.
_MAC = re.compile(
    r"(?<![0-9A-F:.-])(?:[0-9A-F]{2}([:-])[0-9A-F]{2}(?:\1[0-9A-F]{2}){4}"
    r"|[0-9A-F]{4}\.[0-9A-F]{4}\.[0-9A-F]{4})(?![0-9A-F:.-])",
    re.I,
)
# Six hex pairs after a MAC label, written together or apart with spaces ("00 18 DE 9E 62 A6").
_MAC_LABELLED = re.compile(
    r"\bMAC(?:\s*Addr(?:ess)?\.?)?\s*[:#=]?\s*([0-9A-F]{2}(?:[ :-]?[0-9A-F]{2}){5})(?![0-9A-F])",
    re.I,
)
# Fifteen digits, whole or grouped 2-6-6-1 as printed under a barcode; the Luhn check decides.
_IMEI = re.compile(r"(?<![\d-])(\d{2}[ -]?\d{6}[ -]?\d{6}[ -]?\d)(?![\d-])")
# The value after a serial number's label: S/N, SN, Serial (No., Number, #), a service tag.
_SERIAL = re.compile(
    r"(?:\bS\s*/\s*N|\bSN(?=\s*[:#.])|\bSerial(?:\s*(?:No\.?|Number|Num\.?|#))?"
    r"|\bService\s*Tag|\bSVC\s*Tag)\s*[:#.]?\s*([A-Z0-9][A-Z0-9-]{3,39})",
    re.I,
)
# The value after a password's or a network key's label, always with ':' or '='.
_SECRET = re.compile(
    r"(?:\bpass(?:word|wd|code|phrase)|\bpwd|\bPW"
    r"|\bWPA2?(?:[\s-]*(?:PSK|key))?|\bPSK|\bWi-?Fi\s*(?:key|password)"
    r"|\b(?:network|security|wireless|SSID)\s*key)\s*[:=]\s*(\S{2,64})",
    re.I,
)
# A PIN is digits: "PIN: 4821", not "Pin: 24-pin" or "Pin: 40" (a connector's pin count).
_PIN = re.compile(r"\bPIN(?:\s*code)?\s*[:=]\s*(\d{4,12})(?![\w-])", re.I)
# What follows such a label in a listing and is no secret: a rating ("PW: 65W"), a word
# ("WPA2: supported"), an interface named as a serial port ("Serial: RS-232").
_RATING = re.compile(r"\d+(?:\.\d+)?\s*(?:W|V|A|mA|mAh|Wh|Hz|kHz|MHz|GHz)", re.I)
_PLAIN_WORDS = frozenset(
    {
        "yes",
        "no",
        "none",
        "n/a",
        "na",
        "supported",
        "unsupported",
        "enabled",
        "disabled",
        "on",
        "off",
        "required",
        "optional",
        "unknown",
        "included",
        "compatible",
    }
)
_SERIAL_PORT = re.compile(r"RS-?(?:232|422|485)C?", re.I)


TRAILING = ".,;:!?)]}'\""


@dataclass(frozen=True)
class Finding:
    """One private value in a text: its kind and where it is (the value alone, not its label)."""

    kind: Kind
    start: int
    end: int


def luhn(digits: str) -> bool:
    """Whether the digits pass the Luhn check an IMEI carries in its last digit."""
    if not digits.isdigit():
        return False
    total = 0
    for n, ch in enumerate(reversed(digits)):
        d = int(ch)
        if n % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _has_digit(text: str) -> bool:
    return any(c.isdigit() for c in text)


def _trimmed(text: str, start: int, end: int) -> int:
    """Where a value written up to a space ends without the sentence's punctuation."""
    while end - start > 1 and text[end - 1] in TRAILING:
        end -= 1
    return end


def find(text: str) -> list[Finding]:
    """Every private value in the text, in order; where two overlap the earlier, longer one
    stands."""
    found: list[Finding] = []
    for m in _PRODUCT_KEY.finditer(text):
        value = m.group(0)
        if _has_digit(value) and any(c.isalpha() for c in value):
            found.append(Finding("product_key", m.start(), m.end()))
    for m in _MAC.finditer(text):
        found.append(Finding("mac_address", m.start(), m.end()))
    for m in _MAC_LABELLED.finditer(text):
        found.append(Finding("mac_address", m.start(1), m.end(1)))
    for m in _IMEI.finditer(text):
        if luhn(re.sub(r"[ -]", "", m.group(1))):
            found.append(Finding("imei", m.start(1), m.end(1)))
    for m in _SERIAL.finditer(text):
        end = _trimmed(text, m.start(1), m.end(1))
        if _has_digit(m.group(1)) and not _SERIAL_PORT.fullmatch(text[m.start(1) : end]):
            found.append(Finding("serial_number", m.start(1), end))
    for m in _SECRET.finditer(text):
        end = _trimmed(text, m.start(1), m.end(1))
        value = text[m.start(1) : end]
        if value.casefold() not in _PLAIN_WORDS and not _RATING.fullmatch(value):
            found.append(Finding("password", m.start(1), end))
    for m in _PIN.finditer(text):
        found.append(Finding("password", m.start(1), m.end(1)))
    found.sort(key=lambda f: (f.start, -(f.end - f.start)))
    kept: list[Finding] = []
    for f in found:
        if kept and f.start < kept[-1].end:
            continue
        kept.append(f)
    return kept


def kinds_in(text: str) -> list[str]:
    """The kinds of private value in the text, each once, in the order first met."""
    return list(dict.fromkeys(f.kind for f in find(text)))


def mask_value(value: str, kind: str = "serial_number") -> str:
    """A private value as it may be shown: the last four characters of a long identifier,
    nothing of a password or a short value."""
    plain = value.strip()
    if not plain:
        return value
    if kind != "password" and len(plain) >= KEEP_TAIL_FROM:
        return f"{HIDDEN} {plain[-4:]}"
    return HIDDEN


def mask_text(text: str) -> str:
    """The text with every private value in it masked; the rest as it was."""
    findings = find(text)
    if not findings:
        return text
    out: list[str] = []
    at = 0
    for f in findings:
        out.append(text[at : f.start])
        out.append(mask_value(text[f.start : f.end], f.kind))
        at = f.end
    out.append(text[at:])
    return "".join(out)

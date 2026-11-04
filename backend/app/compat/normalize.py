"""Readers that turn the words on a label, a field or a name into the few values a pairing
compares: the memory generation and form, the socket, the board's form, the drive's size and
interface, the bus a card plugs into and what an adapter takes. Each reader returns None (or
nothing) when the text does not say; nothing is guessed."""

import re

# memory generations, in the spelling the rules compare
MEMORY_TYPES = ("DDR2", "DDR3", "DDR3L", "DDR4", "DDR5")
# the drive forms an adapter or an enclosure can take, and a drive can be
DRIVE_FORMS = ("2.5", "3.5", "M.2", "mSATA", "U.2")

# PC3-12800, PC3L-12800, PC4-2666, PC2-6400: the module standard names the generation
_PC = re.compile(r"(?<![A-Z0-9])PC([2-5])(L?)-\d", re.I)
# DDR4, DDR3L, DDR4-2666, LPDDR4 (soldered memory, not a module)
_DDR = re.compile(r"(?<![A-Z0-9])(LP)?DDR([2-5])(L?)(?![A-Z0-9])", re.I)
# 260-pin, 204 pin, 288pin
_PINS = re.compile(r"(?<!\d)(\d{3})\s*-?\s*pins?\b", re.I)
_SODIMM = re.compile(r"\bSO-?DIMMS?\b", re.I)
_DIMM = re.compile(r"(?<![A-Z-])(?:U|R|LR)?DIMMS?\b", re.I)
# what a module's pin count says: (form, generation or None when the count is shared)
PINS = {
    "200": ("SO-DIMM", "DDR2"),
    "204": ("SO-DIMM", "DDR3"),
    "260": ("SO-DIMM", "DDR4"),
    "262": ("SO-DIMM", "DDR5"),
    "184": ("DIMM", None),
    "240": ("DIMM", None),
    "288": ("DIMM", None),
}

_LGA = re.compile(r"\bLGA\s?-?(\d{3,4})\b", re.I)
_SOCKET_NUMBER = re.compile(r"\bSOCKET\s?-?(\d{3,4})\b", re.I)
_AMD = re.compile(r"\b(?:SOCKET\s?)?(AM[2-5]\+?|FM[12]\+?|TR4|sTRX4|sWRX8)(?![A-Z0-9])", re.I)
_SLOT = re.compile(r"\bSLOT\s?-?(1|2|A)\b", re.I)
# Intel sockets that are lands; the rest of the numbered sockets are pins (Socket 370, 478)
LGA_NUMBERS = frozenset({"771", "775", "1150", "1151", "1155", "1156", "1200", "1366", "1700"})
LGA_NUMBERS |= frozenset({"1851", "2011", "2066", "3647", "4677"})

_MATX = re.compile(r"\b(?:MICRO[- ]?ATX|M-?ATX|UATX)\b", re.I)
_ITX = re.compile(r"\bMINI[- ]?ITX\b|\bITX\b", re.I)
_EATX = re.compile(r"\bE-?ATX\b", re.I)
_ATX = re.compile(r"(?<![A-Z-])ATX\b", re.I)

_SIZE = re.compile(r"(?<![\d.])([23]\.5)\s*(?:\"|''|”|-?\s*in(?:ch)?(?:es)?\b)", re.I)
_M2 = re.compile(r"(?<![A-Z0-9])M\.?2(?![0-9])", re.I)
_MSATA = re.compile(r"\bmSATA\b", re.I)
_U2 = re.compile(r"(?<![A-Z0-9])U\.2(?![0-9])", re.I)
_NVME = re.compile(r"\bNVMe\b", re.I)
_SATA = re.compile(r"(?<![A-Z])SATA\b", re.I)
_IDE = re.compile(r"\b(?:IDE|PATA)\b", re.I)
_USB = re.compile(r"\bUSB\b", re.I)

_AGP = re.compile(r"\bAGP\b", re.I)
_PCIE = re.compile(r"\bPCI-?E(?:XPRESS)?\b|\bPCI\s+EXPRESS\b", re.I)
_PCI = re.compile(r"\bPCI\b(?!-?E|\s+EXPRESS)", re.I)

_VOLTS = re.compile(r"(?<![\d.])(3\.3|5)\s?V(?:DC)?\b", re.I)
_TO = re.compile(r"\bto\b", re.I)


def memory_type(text: str) -> str | None:
    """The memory generation the text names: PC3-12800 is DDR3, PC3L DDR3L, PC4-2666 DDR4;
    DDR4-2666 and DDR3L as written; a pin count that only one generation uses. LPDDR is
    soldered memory, never a module, so it says nothing here."""
    m = _PC.search(text)
    if m:
        gen, low = m.group(1), m.group(2)
        return f"DDR{gen}L" if gen == "3" and low else f"DDR{gen}"
    for m in _DDR.finditer(text):
        if m.group(1):
            continue
        gen, low = m.group(2), m.group(3)
        return f"DDR{gen}L" if gen == "3" and low else f"DDR{gen}"
    m = _PINS.search(text)
    if m and m.group(1) in PINS:
        return PINS[m.group(1)][1]
    return None


def memory_form(text: str) -> str | None:
    """SO-DIMM (a laptop stick) or DIMM (a desktop one), from the words or the pin count."""
    if _SODIMM.search(text):
        return "SO-DIMM"
    m = _PINS.search(text)
    if m and m.group(1) in PINS:
        return PINS[m.group(1)][0]
    if _DIMM.search(text):
        return "DIMM"
    return None


def socket(text: str) -> str | None:
    """The processor socket: LGA1155, AM4, Slot 1, Socket 370."""
    m = _LGA.search(text)
    if m:
        return f"LGA{m.group(1)}"
    m = _SLOT.search(text)
    if m:
        return f"Slot {m.group(1).upper()}"
    m = _SOCKET_NUMBER.search(text)
    if m:
        number = m.group(1)
        return f"LGA{number}" if number in LGA_NUMBERS else f"Socket {number}"
    m = _AMD.search(text)
    if m:
        value = m.group(1)
        return value.upper() if value[0].upper() in "AF" else value
    return None


def board_form(text: str) -> str | None:
    """ATX, mATX, ITX or E-ATX."""
    if _MATX.search(text):
        return "mATX"
    if _EATX.search(text):
        return "E-ATX"
    if _ITX.search(text):
        return "ITX"
    if _ATX.search(text):
        return "ATX"
    return None


def drive_size(text: str) -> str | None:
    """2.5 or 3.5 (inches), as a drive or a bay is sized."""
    m = _SIZE.search(text)
    return m.group(1) if m else None


def forms(text: str) -> list[str]:
    """The drive forms the text names, in the order of DRIVE_FORMS."""
    found: list[str] = []
    size = drive_size(text)
    for form, pattern in (("M.2", _M2), ("mSATA", _MSATA), ("U.2", _U2)):
        if pattern.search(text):
            found.append(form)
    if size:
        found.append(size)
    return [f for f in DRIVE_FORMS if f in found]


def interface(text: str) -> str | None:
    """How a drive talks: NVMe, SATA or IDE."""
    if _NVME.search(text):
        return "NVMe"
    if _SATA.search(text) or _MSATA.search(text):
        return "SATA"
    if _IDE.search(text):
        return "IDE"
    return None


def drive_form(text: str) -> str | None:
    """The one form a drive has: its size, or M.2, mSATA or U.2."""
    found = forms(text)
    return found[0] if len(found) == 1 else None


def holds(text: str) -> list[str]:
    """The drive forms an adapter or an enclosure takes. "M.2 and mSATA to SATA" takes M.2 and
    mSATA drives (SATA is where it goes); "M.2 to U.2" plugs into an M.2 slot and takes a U.2
    drive; "M.2 SSD to USB" takes an M.2 drive; without a "to", every form named."""
    parts = _TO.split(text, maxsplit=1)
    if len(parts) == 2:
        right = forms(parts[1])
        return right if right else forms(parts[0])
    return forms(text)


def plug(text: str) -> str | None:
    """What an adapter plugs into: the left of "M.2 to U.2" (an M.2 slot), the right of
    "M.2 to SATA" (a SATA port), a PCIe slot for a card named so."""
    parts = _TO.split(text, maxsplit=1)
    if len(parts) == 2:
        left, right = parts
        if forms(right):
            return "M.2" if _M2.search(left) else None
        if _USB.search(right):
            return "USB"
        if _SATA.search(right):
            return "SATA"
        return None
    if _PCIE.search(text):
        return "PCIe"
    return None


def buses(text: str) -> list[str]:
    """The expansion buses named: AGP, PCIe, PCI."""
    found: list[str] = []
    if _AGP.search(text):
        found.append("AGP")
    if _PCIE.search(text):
        found.append("PCIe")
    if _PCI.search(text):
        found.append("PCI")
    return found


def logic_volts(text: str) -> str | None:
    """A module's or a board's logic level: 5 or 3.3 (volts)."""
    m = _VOLTS.search(text)
    return m.group(1) if m else None

"""Deterministic clean-up of values as printed on labels.

Each normaliser takes the text the model read and returns ``(value, unit)``. Nothing here
guesses: a value that cannot be parsed is returned trimmed, with the default unit.
"""

import re

_NUMBER = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:[.,]\d+)?")
# the range dash may be a hyphen, a tilde, an en dash or an em dash (escaped: alike)
_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:[-~\u2013\u2014]|to)\s*(\d+(?:[.,]\d+)?)", re.I)
_MILLI = re.compile(r"(\d+(?:[.,]\d+)?)\s*m[aA]\b")
# the separator may be x, an asterisk or the multiplication sign
_TIMES = "x*" + chr(0xD7)
_BARREL = re.compile(rf"(\d+(?:[.,]\d+)?)\s*[{_TIMES}]\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?")
_CODE_PREFIX = re.compile(
    r"^(?:P/?N|PART(?: NO\.?| NUMBER)?|MODEL(?: NO\.?)?|MOD\.?)\s*[:#]?\s*", re.I
)
_LIST_SPLIT = re.compile(r"[,;/|]+|\s{2,}")
# grouping, not a decimal mark: "1,000" reads as thousands, "19,5" still as 19.5
_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")


def strip_thousands(text: str) -> str:
    """A label's thousands grouping removed; a decimal comma is not grouping and stays."""
    return _THOUSANDS.sub(lambda m: m.group(0).replace(",", ""), text)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _num(text: str) -> str:
    """Format a number as printed: no trailing zeros, dot as the decimal mark."""
    value = float(strip_thousands(text).replace(",", "."))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _first_number(text: str) -> str | None:
    m = _NUMBER.search(text)
    return _num(m.group(0)) if m else None


def _volts(text: str) -> tuple[str, str]:
    n = _first_number(text)
    return (n, "V") if n else (_clean(text), "V")


def _volts_range(text: str) -> tuple[str, str]:
    m = _RANGE.search(text)
    if m:
        return f"{_num(m.group(1))}-{_num(m.group(2))}", "V"
    return _volts(text)


def _amps(text: str) -> tuple[str, str]:
    m = _MILLI.search(text)
    if m:
        milli = float(strip_thousands(m.group(1)).replace(",", "."))
        return _num(str(milli / 1000)), "A"
    n = _first_number(text)
    return (n, "A") if n else (_clean(text), "A")


def _watts(text: str) -> tuple[str, str]:
    n = _first_number(text)
    return (n, "W") if n else (_clean(text), "W")


def _code(text: str) -> tuple[str, str]:
    code = _CODE_PREFIX.sub("", _clean(text)).upper()
    return re.sub(r"[^A-Z0-9./_-]+", "", code), ""


def _connector(text: str) -> tuple[str, str]:
    t = _clean(text).lower()
    if re.search(r"usb[\s-]?c|type[\s-]?c", t):
        return "usb-c", ""
    m = _BARREL.search(t)
    if m:
        return f"barrel {_num(m.group(1))} x {_num(m.group(2))} mm", ""
    return t, ""


_POLARITY_NEGATIVE = re.compile(
    r"cent(?:re|er)\s+negative|-\s*cent(?:re|er)|cent(?:re|er)\s*-|\bnegative\b|\bneg\b"
)
_POLARITY_POSITIVE = re.compile(
    r"cent(?:re|er)\s+positive|\+\s*cent(?:re|er)|cent(?:re|er)\s*\+|\bpositive\b|\bpos\b"
)


def _polarity(text: str) -> tuple[str, str]:
    t = _clean(text).lower()
    if _POLARITY_NEGATIVE.search(t):
        return "center negative", ""
    if _POLARITY_POSITIVE.search(t):
        return "center positive", ""
    return t, ""


def _list(text: str) -> tuple[str, str]:
    parts = [p.strip().upper() for p in _LIST_SPLIT.split(text) if p.strip()]
    if len(parts) == 1 and " " in parts[0]:
        parts = parts[0].split()
    return ", ".join(dict.fromkeys(parts)), ""


# what a listing, a label or an owner calls a material, read as the one word a rule compares
_METALS = frozenset(
    (
        "stainless",
        "steel",
        "aluminium",
        "aluminum",
        "alloy",
        "brass",
        "bronze",
        "copper",
        "chrome",
        "metal",
        "metals",
        "iron",
        "nickel",
        "titanium",
        "zinc",
    )
)
_PLASTICS = frozenset(
    (
        "plastic",
        "plastics",
        "abs",
        "nylon",
        "polyamide",
        "pom",
        "acetal",
        "delrin",
        "polypropylene",
        "polyethylene",
        "polycarbonate",
        "polystyrene",
        "tritan",
        "pvc",
        "acrylic",
        "resin",
        "silicone",
        "rubber",
    )
)
# a word before a material that says it is not that material: "non-metal", "no plastic"
_NOT_BEFORE = frozenset(("non", "no", "not", "without"))
# Only simple material declarations establish the whole part's material.
_MATERIAL_WORDS = (
    _METALS
    | _PLASTICS
    | frozenset(
        ("all", "solid", "throughout", "die", "cast", "bpa", "lead", "free", "non", "stick")
    )
)


def _material(text: str) -> tuple[str, str]:
    """``metal`` or ``plastic`` when the words say so, else the text cleaned: the rule for a
    material compares one word, so "all-metal", "stainless steel" and "metal throughout" are
    one value, as are "ABS plastic", "POM" and "BPA-free plastic". A mix ("metal rod, plastic
    head"), a part or a surface ("mostly metal", "chrome finish") and a negation ("non-metal",
    "no plastic", "plastic-free") stay as written, so a rule asking for metal does not pass
    them."""
    low = _clean(text).lower()
    words = re.findall(r"[a-z]+", low)
    found: set[str] = set()
    for i, word in enumerate(words):
        kind = "metal" if word in _METALS else "plastic" if word in _PLASTICS else ""
        if not kind:
            continue
        before = words[i - 1] if i else ""
        after = words[i + 1] if i + 1 < len(words) else ""
        if before in _NOT_BEFORE or after == "free":
            return low, ""
        found.add(kind)
    if len(found) == 1 and set(words) <= _MATERIAL_WORDS and "?" not in low:
        return found.pop(), ""
    return low, ""


def _text(text: str) -> tuple[str, str]:
    return _clean(text), ""


_NORMALIZERS = {
    "volts": _volts,
    "volts_range": _volts_range,
    "amps": _amps,
    "watts": _watts,
    "code": _code,
    "connector": _connector,
    "polarity": _polarity,
    "list": _list,
    "material": _material,
    "text": _text,
}


def normalize(kind: str, text: str, *, default_unit: str = "") -> tuple[str, str]:
    """Normalise ``text`` with the named normaliser; unknown names fall back to text."""
    value, unit = _NORMALIZERS.get(kind, _text)(text)
    return value, unit or default_unit

"""Whether parts physically work together: each item read once into the few values a pairing
compares, then one rule per pair of roles (memory in a board or a laptop, a processor in a
board, a drive in a bay, a port or an adapter, a card in a slot, a module in an enclosure),
each answering pass, fail or unknown. Unknown is never a pass: a value nobody recorded is a
question to check. Nothing here calls a model; the data is in app/compat/data."""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cache
from itertools import product
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.compat import normalize as norm
from app.inventory.schema import Item
from app.privacy.text import private_field

DATA_DIR = Path(__file__).parent / "data"
State = Literal["pass", "fail", "unknown"]
RANK: dict[str, int] = {"pass": 2, "unknown": 1, "fail": 0}
# the attributes an item's own field may state outright, by the reader that spells them
FIELD_READERS: dict[str, Callable[[str], Any]] = {
    "memory_type": norm.memory_type,
    "memory_form": norm.memory_form,
    "socket": norm.socket,
    "board_form": norm.board_form,
    "drive_form": norm.drive_form,
    "bay": norm.drive_size,
    "interface": norm.interface,
    "holds": norm.holds,
    "plug": norm.plug,
    "slots": lambda t: norm.buses(t) + norm.forms(t) + (["SATA"] if norm.interface(t) else []),
    "logic_volts": norm.logic_volts,
}
# the measured sizes a housing compares, in millimeters (the generic profile's features)
DIM_FIELDS = ("width", "height", "depth")
# the fields a known part is looked up by, besides the name
NUMBER_FIELDS = ("model_number", "part_number")
# what a part is checked against, by its role: a stick goes in a board or a laptop, a drive in
# a bay, a port, an adapter or an enclosure, a module on a microcontroller board or in a box
PART_HOSTS: dict[str, tuple[str, ...]] = {
    "memory": ("board", "laptop"),
    "processor": ("board",),
    "drive": ("board", "laptop", "adapter", "enclosure"),
    "card": ("board",),
    "adapter": ("board",),
    "module": ("controller", "enclosure"),
    "controller": ("enclosure",),
}
# the roles that hold drives, and are a missing part's reason when none of theirs is owned
HOLDERS = ("adapter", "enclosure")
# a card names a few kinds, each owned a few times: the assignments tried are bounded
MAX_CHOICES = 6
MAX_ASSIGNMENTS = 4096


class Pairing(BaseModel):
    """One pairing checked: which part with which host, the answer and why, and what to do
    when it fails (an item of yours that fits, or the part to search for)."""

    rule: str = Field(description="memory, socket, drive, slot, plug, housing, voltage, missing")
    state: State
    part_id: int | None
    part: str
    host_id: int | None
    host: str
    reason: str
    fix: str = Field(default="", description="what to do about a failure; empty on a pass")
    search: str = Field(default="", description="the part to search for, when none of yours fits")


@dataclass(frozen=True)
class Reading:
    """An item as the rules read it."""

    id: int
    name: str
    item_type: str
    role: str | None
    attrs: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        return self.attrs.get(key)


@dataclass(frozen=True)
class Result:
    state: State
    rule: str
    reason: str
    # what would take the part's place, and the host's, when this pair fails
    need_part: str = ""
    need_host: str = ""
    # which side a failure is fixed on: the stick, not the laptop; the box, not the module
    replace: Literal["part", "host"] = "part"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9.+-]+", text.lower())


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _ends_with(kind: str, wanted: str) -> bool:
    have = [_singular(w) for w in _words(kind)]
    want = [_singular(w) for w in _words(wanted)]
    return bool(want) and have[-len(want) :] == want


class Rules:
    """The roles and the known parts, loaded once from app/compat/data."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        with (data_dir / "roles.yaml").open(encoding="utf-8") as fh:
            roles = yaml.safe_load(fh)
        with (data_dir / "parts.yaml").open(encoding="utf-8") as fh:
            parts = yaml.safe_load(fh)
        self.not_kinds: list[str] = list(roles.get("not", []))
        self.roles: dict[str, dict[str, Any]] = dict(roles["roles"])
        self.parts: list[tuple[re.Pattern[str], dict[str, Any]]] = [
            (re.compile(p["match"], re.I), dict(p["attrs"])) for p in parts["parts"]
        ]
        for role, spec in self.roles.items():
            if not spec.get("kinds"):
                raise ValueError(f"role {role!r} names no kinds")
        unknown = {r for hosts in PART_HOSTS.values() for r in hosts} - set(self.roles)
        if unknown:
            raise ValueError(f"PART_HOSTS names roles with no data: {sorted(unknown)}")

    def role_of(self, item_type: str) -> str | None:
        if any(_ends_with(item_type, k) for k in self.not_kinds):
            return None
        best: tuple[int, str] | None = None
        for role, spec in self.roles.items():
            for kind in spec["kinds"]:
                # the longest kind that fits wins: "microcontroller board" over "board"
                if _ends_with(item_type, kind):
                    size = len(_words(kind))
                    if best is None or size > best[0]:
                        best = (size, role)
        return best[1] if best else None

    def read(self, item: Item) -> Reading:
        """The item's attributes: a field that states one outright, then the known part its
        model or part number (or name) is, then what its accepted values, its name and its
        type say, then what its role says by default."""
        role = self.role_of(item.item_type)
        values = {
            k: f"{a.value} {a.unit}".strip()
            for k, a in item.fields.items()
            if a.review == "accepted" and not private_field(k)
        }
        attrs: dict[str, Any] = {}
        for key, reader in FIELD_READERS.items():
            if key in values:
                found = reader(values[key])
                if found:
                    attrs[key] = found
        numbers = [values[k] for k in NUMBER_FIELDS if k in values] + [item.name]
        for pattern, known in self.parts:
            if any(pattern.search(n.strip()) for n in numbers):
                for key, value in known.items():
                    attrs.setdefault(key, value)
                break
        # the label's values first, then the owner's name for it, then its type
        texts = [v for k, v in values.items() if k not in FIELD_READERS]
        texts += [item.name, item.item_type]
        _read_texts(attrs, role, texts, [item.name, item.item_type])
        spec = self.roles.get(role or "", {})
        words = set(_words(f"{item.item_type} {item.name}"))
        for hint in spec.get("hints", []):
            if words & {w.lower() for w in hint["words"]}:
                for key, value in hint["attrs"].items():
                    attrs.setdefault(key, value)
        for key, value in spec.get("defaults", {}).items():
            attrs.setdefault(key, value)
        dims = [_mm(values.get(k, "")) for k in DIM_FIELDS]
        if all(d is not None for d in dims):
            attrs.setdefault("dims", dims)
        return Reading(item.id, item.name, item.item_type, role, attrs)


@cache
def shared() -> "Rules":
    """The shipped rules, loaded once per process."""
    return Rules()


def _mm(text: str) -> float | None:
    """A measured size in millimeters, as the measuring step stores it."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mm)?\s*$", text)
    return float(m.group(1)) if m else None


def _first(texts: Iterable[str], reader: Callable[[str], Any]) -> Any:
    for text in texts:
        found = reader(text)
        if found:
            return found
    return None


def _read_texts(attrs: dict[str, Any], role: str | None, texts: list[str], own: list[str]) -> None:
    """What the free text says, read only for the attributes the role has."""

    def put(key: str, reader: Callable[[str], Any], where: list[str] = texts) -> None:
        if key not in attrs:
            found = _first(where, reader)
            if found:
                attrs[key] = found

    if role in ("memory", "board", "laptop"):
        put("memory_type", norm.memory_type)
        put("memory_form", norm.memory_form)
    if role in ("processor", "board"):
        put("socket", norm.socket)
    if role == "board":
        put("board_form", norm.board_form)
    if role == "laptop":
        put("bay", norm.drive_size)
    if role == "drive":
        put("drive_form", norm.drive_form)
        put("interface", norm.interface)
    if role in HOLDERS:
        # what it takes is in its name or type, not in a connector field: the connector of an
        # M.2 to U.2 adapter is the M.2 edge it plugs in by
        put("holds", norm.holds, own)
        put("plug", norm.plug, own)
    if role == "card":
        put("bus", lambda t: next(iter(norm.buses(t)), None))
    if role in ("module", "controller"):
        put("logic_volts", norm.logic_volts)


# --- the rules, one per pair of roles ----------------------------------------------------------


# letters said with a vowel first: "an LGA1155", "an M.2", "an SSD", "an NVMe"; "a U.2"
_AN_PREFIXES = ("LGA", "M.2", "mSATA", "NVMe", "SSD", "HDD", "HDMI", "FM", "8 ", "11", "18")


def _an(phrase: str) -> str:
    if phrase.startswith(("U.2", "USB", "uni", "use")):
        return f"a {phrase}"
    if phrase[:1].lower() in "aeiou" or phrase.startswith(_AN_PREFIXES):
        return f"an {phrase}"
    return f"a {phrase}"


def _spaced(*parts: str | None) -> str:
    return " ".join(p for p in parts if p)


def _host_word(host: Reading) -> str:
    return "laptop" if host.role == "laptop" else "board"


def _check(*whats: str) -> str:
    """An unknown, said as what to check: a value nobody recorded is never a pass."""
    return f"check {' and '.join(whats)} (not recorded)"


def memory_need(host: Reading) -> str:
    """The memory a host takes, as a search would title it: "DDR3 SO-DIMM laptop memory"."""
    form = host.get("memory_form")
    where = "laptop" if form == "SO-DIMM" or host.role == "laptop" else "desktop"
    return _spaced(host.get("memory_type"), form, f"{where} memory")


def processor_need(host: Reading) -> str:
    socket = host.get("socket")
    return f"{socket} processor" if socket else "processor that fits the board's socket"


def drive_need(holder: Reading) -> str:
    holds = holder.get("holds") or []
    if not holds:
        return "drive"
    sized = [f"{h} inch" if h in ("2.5", "3.5") else h for h in holds]
    return f"{' or '.join(sized)} drive"


def memory_rule(part: Reading, host: Reading) -> Result:
    pt, pf = part.get("memory_type"), part.get("memory_form")
    ht, hf = host.get("memory_type"), host.get("memory_form")
    word = _host_word(host)
    what = _spaced(pt, pf) or "memory"
    need_part = memory_need(host)
    need_host = f"{word} that takes {_spaced(pt, pf) or 'this memory'}s"
    if pf and hf and pf != hf:
        return Result(
            "fail",
            "memory",
            f"{what} in {_an(word)} that takes {_spaced(ht, hf)}s",
            need_part,
            need_host,
        )
    if pt and ht and pt != ht and not (pt == "DDR3L" and ht == "DDR3"):
        if pt == "DDR3" and ht == "DDR3L":
            return Result(
                "unknown",
                "memory",
                f"DDR3 in a DDR3L {word}: check it runs 1.5 V sticks",
                need_part,
                need_host,
            )
        return Result("fail", "memory", f"{what} in {_an(_spaced(ht, word))}", need_part, need_host)
    if pt and ht and pf and hf:
        extra = " (DDR3L sticks also run at DDR3's 1.5 V)" if pt != ht else ""
        return Result("pass", "memory", f"{what} in {_an(_spaced(ht, hf, word))}{extra}")
    whats = []
    if not pt or not pf:
        whats.append(f"which memory {part.name} is")
    if not ht or not hf:
        whats.append(f"which memory {host.name} takes")
    return Result("unknown", "memory", _check(*whats), need_part, need_host)


def socket_rule(part: Reading, host: Reading) -> Result:
    ps, hs = part.get("socket"), host.get("socket")
    need_part, need_host = processor_need(host), f"board with a {ps} socket" if ps else ""
    if ps and hs:
        if ps == hs:
            return Result("pass", "socket", f"{ps} processor in {_an(hs)} socket")
        return Result(
            "fail",
            "socket",
            f"{_an(ps)} processor does not fit {_an(hs)} board",
            need_part,
            need_host,
        )
    unknown = part.name if not ps else host.name
    return Result("unknown", "socket", _check(f"the socket of {unknown}"), need_part, need_host)


def _sized(form: str) -> str:
    return f"{form} inch" if form in ("2.5", "3.5") else form


def drive_rule(part: Reading, host: Reading) -> Result:
    df, di = part.get("drive_form"), part.get("interface")
    if host.role == "laptop":
        bay, bay_if = host.get("bay"), host.get("interface")
        need = _spaced(f"{bay} inch" if bay else "2.5 inch", bay_if or "SATA", "drive")
        if df in ("3.5", "U.2"):
            return Result(
                "fail", "drive", f"{_an(_sized(df))} drive in a laptop's drive bay", need, ""
            )
        if df == "2.5" and bay == "2.5":
            if di and bay_if and di != bay_if:
                return Result("fail", "drive", f"{di} drive in a {bay_if} laptop bay", need, "")
            if di and bay_if:
                return Result("pass", "drive", f"2.5 inch {di} drive in a 2.5 inch {di} bay")
        whats = [] if bay else [f"the drive bay of {host.name}"]
        if not df:
            whats.append(f"the size of {part.name}")
        if not whats:
            whats.append(f"the interface of {part.name}")
        return Result("unknown", "drive", _check(*whats), need, "")
    if host.role == "board":
        slots = host.get("slots") or []
        if df in ("M.2", "mSATA", "U.2"):
            if not slots:
                return Result("unknown", "drive", _check(f"the slots of {host.name}"))
            if df in slots:
                return Result("pass", "drive", f"{df} drive in the board's {df} slot")
            return Result(
                "fail",
                "drive",
                f"{_an(df)} drive on a board without {_an(df)} slot",
                "SATA drive",
                f"{df} adapter",
            )
        if di and slots:
            if di == "SATA" and "SATA" in slots:
                return Result("pass", "drive", "SATA drive on the board's SATA ports")
            if di not in slots and not (di == "NVMe" and "M.2" in slots):
                return Result(
                    "fail", "drive", f"{_an(di)} drive on a board without {di} ports", "SATA drive"
                )
        what = f"the ports of {host.name}" if not slots else f"the interface of {part.name}"
        return Result("unknown", "drive", _check(what))
    # an adapter or an enclosure: it takes the forms it names
    holds = host.get("holds") or []
    if not holds:
        return Result("unknown", "drive", _check(f"what {host.name} takes"))
    if not df:
        return Result("unknown", "drive", _check(f"the form of {part.name}"), drive_need(host))
    if df in holds:
        return Result("pass", "drive", f"{_an(_sized(df))} drive in {_an(host.item_type)} for it")
    takes = " or ".join(_sized(h) for h in holds)
    return Result(
        "fail",
        "drive",
        f"{_an(_sized(df))} drive in {_an(host.item_type)} that takes {takes} drives",
        drive_need(host),
        f"{_sized(df)} drive enclosure or adapter",
    )


def slot_rule(part: Reading, host: Reading) -> Result:
    bus, slots = part.get("bus"), host.get("slots") or []
    if not bus or not slots:
        what = f"the slot {part.name} needs" if not bus else f"the slots of {host.name}"
        return Result("unknown", "slot", _check(what))
    if bus in slots:
        return Result("pass", "slot", f"{bus} card in a {bus} slot")
    return Result(
        "fail",
        "slot",
        f"{_an(bus)} card on a board without {_an(bus)} slot",
        f"{slots[0]} {part.item_type}",
        f"board with {_an(bus)} slot",
    )


def plug_rule(part: Reading, host: Reading) -> Result | None:
    plug, slots = part.get("plug"), host.get("slots") or []
    if plug in (None, "USB"):
        return None
    if not slots:
        return Result("unknown", "plug", _check(f"the slots of {host.name}"))
    if plug in slots:
        return Result(
            "pass", "plug", f"plugs into the board's {plug} {'port' if plug == 'SATA' else 'slot'}"
        )
    return Result(
        "fail",
        "plug",
        f"needs {_an(plug)} slot the board does not have",
        "",
        f"board with {_an(plug)} slot",
    )


def _dims(reading: Reading) -> list[float] | None:
    dims = reading.get("dims")
    return sorted(dims) if dims and len(dims) == 3 else None


def housing_rule(part: Reading, host: Reading) -> Result:
    """Something put inside an enclosure: it holds what it is made for and nothing larger than
    itself."""
    holds = host.get("holds") or []
    box = "project box"
    if holds:
        takes = " or ".join(_sized(h) for h in holds)
        return Result(
            "fail",
            "housing",
            f"not a drive: {_an(host.item_type)} made for {takes} drives holds nothing else",
            "",
            box,
            "host",
        )
    inside, outside = _dims(part), _dims(host)
    if inside and outside:
        if all(a <= b for a, b in zip(inside, outside, strict=True)):
            return Result("pass", "housing", f"{part.item_type} fits inside by its measured size")
        return Result(
            # the box's type, not its name: a box refused for a build is not on it, and its
            # name may be one the demo visitor is not shown
            "fail",
            "housing",
            f"{part.item_type} is larger than {_an(host.item_type)} can hold",
            "",
            box,
            "host",
        )
    return Result("unknown", "housing", _check(f"whether {part.name} fits inside {host.name}"))


def voltage_rule(part: Reading, host: Reading) -> Result | None:
    pv, hv = part.get("logic_volts"), host.get("logic_volts")
    if not pv or not hv:
        return None
    if pv == hv:
        return Result("pass", "voltage", f"{pv} V module on a {hv} V board")
    if pv == "5":
        return Result(
            "fail", "voltage", f"5 V module on a {hv} V board", f"{hv} V {part.item_type}"
        )
    return Result("unknown", "voltage", f"{pv} V module on a {hv} V board: check it takes {hv} V")


def check(part: Reading, host: Reading) -> Result | None:
    """The rule for this part in this host, or None when no rule pairs their roles."""
    pr, hr = part.role, host.role
    if pr is None or hr not in PART_HOSTS.get(pr, ()):
        return None
    if pr == "memory":
        return memory_rule(part, host)
    if pr == "processor":
        return socket_rule(part, host)
    if pr == "drive":
        return drive_rule(part, host)
    if pr == "card":
        return slot_rule(part, host)
    if pr == "adapter":
        return plug_rule(part, host)
    if hr == "enclosure":
        return housing_rule(part, host)
    if pr == "module" and hr == "controller":
        return voltage_rule(part, host)
    return None


# --- sets of items: a project's allocations, a card's items ----------------------------------


def _pairing(part: Reading, host: Reading, result: Result) -> Pairing:
    return Pairing(
        rule=result.rule,
        state=result.state,
        part_id=part.id,
        part=part.name,
        host_id=host.id,
        host=host.name,
        reason=result.reason,
    )


def best_hosts(readings: list[Reading]) -> list[tuple[Reading, Reading, Result]]:
    """Each part with the host in the set that suits it best (a pass over an unknown over a
    fail): a drive on a board's SATA port is not failed by an M.2 adapter beside it."""
    out: list[tuple[Reading, Reading, Result]] = []
    for part in readings:
        results: list[tuple[Reading, Result]] = []
        for host in readings:
            if host.id == part.id:
                continue
            found = check(part, host)
            if found is not None:
                results.append((host, found))
        if results:
            host, result = max(results, key=lambda hr: RANK[hr[1].state])
            out.append((part, host, result))
    return out


def fitting(part: Reading, readings: Iterable[Reading]) -> Reading | None:
    """A host among ``readings`` this part passes in."""
    for host in readings:
        found = check(part, host)
        if found is not None and found.state == "pass":
            return host
    return None


def fitting_part(host: Reading, readings: Iterable[Reading], role: str) -> Reading | None:
    """An item of ``role`` among ``readings`` that passes in this host."""
    for part in readings:
        if part.role != role or part.id == host.id:
            continue
        found = check(part, host)
        if found is not None and found.state == "pass":
            return part
    return None


def fix_line(need: str, found: Reading | None) -> tuple[str, str]:
    """What to do about a failed pairing: an item of yours that fits, or the part to search
    for. Returns the line and the search's words (empty when yours will do)."""
    if found is not None:
        return f"use {found.name} instead, it fits", ""
    if not need:
        return "", ""
    return f"needs {_an(need)} \u2014 not in your inventory; search it", need


def _fix(
    part: Reading, host: Reading, result: Result, others: list[Reading], *, keep: int | None
) -> tuple[str, str, int]:
    """The fix for a failed pairing and the id of the item it replaces: the side the rule
    says, unless that side is ``keep`` (the item a card is about); an item of yours that fits
    in its place first, else the part to search for."""
    side = result.replace
    if keep == part.id:
        side = "host"
    elif keep == host.id:
        side = "part"
    if side == "part":
        swap = fitting_part(host, others, part.role or "")
        line, search = fix_line(result.need_part or result.need_host, swap)
        return line, search, part.id
    swap = fitting(part, [o for o in others if o.role == host.role])
    line, search = fix_line(result.need_host or result.need_part, swap)
    return line, search, host.id


def missing_line(holder: Reading, inside: list[Reading], owned: list[Reading]) -> Pairing | None:
    """An adapter or enclosure with nothing of yours to take: the drive it is for is a missing
    part, not something you have."""
    if holder.role not in HOLDERS or not holder.get("holds"):
        return None
    if fitting_part(holder, inside, "drive") is not None:
        return None
    yours = fitting_part(holder, owned, "drive")
    need = drive_need(holder)
    if yours is not None:
        line, search = f"use {yours.name}, it fits", ""
        reason = f"no {need} with it here"
    else:
        line, search = fix_line(need, None)
        reason = f"nothing you own goes in it: it takes {_an(need)}"
    return Pairing(
        rule="missing",
        state="fail",
        part_id=None,
        part=need,
        host_id=holder.id,
        host=holder.name,
        reason=reason,
        fix=line,
        search=search,
    )


def set_pairings(
    readings: list[Reading], owned: list[Reading], *, holders: Iterable[int] | None = None
) -> list[Pairing]:
    """Every pairing in a set of items, each part with its best host, a failure with its fix
    from what else is owned; and for each holder in ``holders`` (every one when None) the
    drive it is for when none of the set's fits it."""
    ids = {r.id for r in readings}
    others = [o for o in owned if o.id not in ids]
    out: list[Pairing] = []
    for part, host, result in best_hosts(readings):
        pairing = _pairing(part, host, result)
        if result.state == "fail":
            pairing.fix, pairing.search, _ = _fix(part, host, result, others, keep=None)
        out.append(pairing)
    wanted = set(ids if holders is None else holders)
    for holder in readings:
        if holder.id in wanted:
            line = missing_line(holder, readings, others)
            if line is not None:
                out.append(line)
    return out


@dataclass
class CardCheck:
    """A card's "with what you have", checked: the kinds that hold, the pairings, and the kinds
    left out because no item of that kind works with the rest."""

    kept: list[str]
    pairings: list[Pairing]
    dropped: list[str]


def _score(pairings: list[Pairing]) -> tuple[int, int, int]:
    fails = sum(1 for p in pairings if p.state == "fail")
    unknowns = sum(1 for p in pairings if p.state == "unknown")
    passes = sum(1 for p in pairings if p.state == "pass")
    return (-fails, -unknowns, passes)


def card_check(anchor: Reading, kinds: list[str], owned: list[Reading]) -> CardCheck:
    """The card's item with one owned item of each kind it names, chosen so the set works
    together as well as it can; a failure is fixed on the other item's side (the card is about
    this one), and a kind whose item still fails is taken out of "with what you have"."""
    options: list[list[Reading | None]] = []
    for kind in kinds:
        cands = [
            o for o in owned if o.item_type.casefold() == kind.casefold() and o.id != anchor.id
        ]
        options.append(list(cands[:MAX_CHOICES]) or [None])
    best: tuple[tuple[int, int, int], list[Reading], list[tuple[Reading, Reading, Result]]] | None
    best = None
    for n, combo in enumerate(product(*options)):
        if n >= MAX_ASSIGNMENTS:
            break
        chosen = [anchor, *(c for c in combo if c is not None)]
        found = best_hosts(chosen)
        score = _score([_pairing(p, h, r) for p, h, r in found])
        if best is None or score > best[0]:
            best = (score, chosen, found)
    chosen, found = (best[1], best[2]) if best else ([anchor], [])
    by_id = {r.id: r for r in chosen}
    others = [o for o in owned if o.id not in by_id]
    pairings: list[Pairing] = []
    replaced: set[int] = set()
    for part, host, result in found:
        pairing = _pairing(part, host, result)
        if result.state == "fail":
            # the card's item stays: the other side is what changes
            pairing.fix, pairing.search, gone = _fix(part, host, result, others, keep=anchor.id)
            replaced.add(gone)
        pairings.append(pairing)
    line = missing_line(anchor, chosen, others)
    if line is not None:
        pairings.append(line)
    pairings = merged(pairings)
    kept: list[str] = []
    dropped: list[str] = []
    for kind, item in zip(kinds, _picked(kinds, chosen, anchor), strict=True):
        (dropped if item is not None and item.id in replaced else kept).append(kind)
    return CardCheck(kept=kept, pairings=pairings, dropped=dropped)


def merged(pairings: list[Pairing]) -> list[Pairing]:
    """Failures of several parts in one host for one reason said once: the board, the clock
    and the sensor that do not go in a drive enclosure need one project box."""
    out: list[Pairing] = []
    for p in pairings:
        same = next(
            (
                o
                for o in out
                if p.state == "fail"
                and o.state == "fail"
                and o.rule == p.rule == "housing"
                and o.host_id == p.host_id
                and o.fix == p.fix
            ),
            None,
        )
        if same is None:
            out.append(p.model_copy())
            continue
        same.part = f"{same.part}, {p.part}"
    return out


def _picked(kinds: list[str], chosen: list[Reading], anchor: Reading) -> list[Reading | None]:
    rest = [c for c in chosen if c.id != anchor.id]
    out: list[Reading | None] = []
    for kind in kinds:
        match = next((c for c in rest if c.item_type.casefold() == kind.casefold()), None)
        if match is not None:
            rest.remove(match)
        out.append(match)
    return out

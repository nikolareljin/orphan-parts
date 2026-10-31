"""The search plan for a need: several phrasings a seller might have used, one match pattern
over listing text, and the words that rule a listing out. Marketplace has no public search API
and automating it is against its terms, so the plan is links the owner opens and a pattern the
app applies to the listings the owner brings back. Marketplace's own search box takes words,
not regular expressions.

The pattern runs on Python's ``re``, which backtracks and has no timeout, so it is checked
before it is compiled: bounded length, no backreferences, and none of the shapes that make a
backtracking engine run away (a repeated group that repeats or branches inside, an open-ended
``.*``, two open-ended repeats side by side, too many open-ended repeats in all). The text it
runs over is bounded too."""

import re
from dataclasses import dataclass

MAX_PATTERN_LEN = 300
MAX_PHRASINGS = 6
MIN_PHRASINGS = 3
PHRASING_MAX = 120
WHY_MAX = 200
MAX_EXCLUSIONS = 20
EXCLUSION_MAX = 40
# open-ended repeats (*, +, {n,}) one pattern may carry
MAX_UNBOUNDED = 6
# the most of a listing the pattern and the exclusions are run over
SCAN_MAX = 4000
# what rules a listing out unless the owner says otherwise
DEFAULT_EXCLUSIONS = ["for parts", "parts only", "broken", "not working", "does not work"]

_PRICE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d{1,7})(?:\.(\d{1,2}))?"
    r"|\b(\d{1,3}(?:,\d{3})+|\d{1,7})(?:\.(\d{1,2}))?\s?(?:usd|dollars|bucks)\b",
    re.IGNORECASE,
)
_FREE = re.compile(r"\bfree\b", re.IGNORECASE)


class PatternError(ValueError):
    """The pattern cannot be used: it does not compile, is too long, or could run away."""


@dataclass(frozen=True)
class Hit:
    kind: str  # "match" or "excluded"
    start: int  # offsets in characters (code points) of the listing text
    end: int
    text: str


@dataclass(frozen=True)
class Score:
    verdict: str  # "fits", "maybe", "no"
    matched: bool | None  # None when there is no pattern to match
    hits: list[Hit]
    excluded: list[str]
    price: float | None
    price_ok: bool | None
    reasons: list[str]


@dataclass
class _Group:
    repeats: bool = False  # holds a repeat (or a group that does)
    branches: bool = False  # holds a | (or a group that does)


def _quantifier(pattern: str, i: int) -> tuple[int, bool, bool]:
    """The quantifier starting at ``i``, if any: (its length, whether it repeats more than
    once, whether it is open-ended). A lazy or possessive suffix is part of it."""
    if i >= len(pattern):
        return 0, False, False
    ch = pattern[i]
    length, repeats, unbounded = 0, False, False
    if ch in "*+":
        length, repeats, unbounded = 1, True, True
    elif ch == "?":
        length = 1
    elif ch == "{":
        found = re.match(r"\{(\d*)(,?)(\d*)\}", pattern[i:])
        if found is None:
            return 0, False, False  # a literal brace
        low, comma, high = found.groups()
        length = found.end()
        if comma and not high:
            repeats = unbounded = True
        else:
            top = int(high or low or "0")
            repeats = top > 1
    if length and pattern[i + length : i + length + 1] in ("?", "+"):
        length += 1
    return length, repeats, unbounded


def check_shape(pattern: str) -> None:
    """Raise PatternError for a shape that backtracks without end on text that nearly
    matches: ``(a+)+``, ``(.*)*``, ``(\\w+\\s?)*``, ``(a|aa)+``, ``.*`` and ``\\d+\\d+``."""
    stack: list[_Group] = [_Group()]
    unbounded_total = 0
    previous_open = False  # the atom before this one carried an open-ended repeat
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        atom: str | None = None
        group: _Group | None = None
        if ch == "\\":
            if i + 1 < n and pattern[i + 1] in "123456789":
                raise PatternError("backreferences are not used here")
            atom = "escape"
            i += 2
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1  # a ] first in the class is a literal
            while j < n and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            atom = "class"
            i = j + 1
        elif ch == "(":
            if pattern.startswith("(?P=", i):
                raise PatternError("backreferences are not used here")
            stack.append(_Group())
            previous_open = False
            i += 1
            continue
        elif ch == ")":
            if len(stack) == 1:
                raise PatternError("the pattern does not compile: unbalanced parenthesis")
            group = stack.pop()
            atom = "group"
            i += 1
        elif ch == "|":
            stack[-1].branches = True
            previous_open = False
            i += 1
            continue
        elif ch in "^$":
            previous_open = False
            i += 1
            continue
        else:
            atom = "dot" if ch == "." else "char"
            i += 1
        length, repeats, unbounded = _quantifier(pattern, i)
        i += length
        if group is not None:
            if repeats and group.repeats:
                raise PatternError(
                    "a repeated group that repeats inside, such as (a+)+, is refused"
                )
            if repeats and group.branches:
                raise PatternError(
                    "a repeated group with alternatives, such as (a|ab)+, is refused;"
                    " a character class such as [-\\s] does the same safely"
                )
            parent = stack[-1]
            parent.repeats = parent.repeats or group.repeats or repeats
            parent.branches = parent.branches or group.branches
        elif repeats:
            stack[-1].repeats = True
        if unbounded:
            if atom == "dot":
                raise PatternError("an open-ended .* or .+ is refused; write .{0,40}")
            if previous_open:
                raise PatternError("two open-ended repeats side by side are refused")
            unbounded_total += 1
        previous_open = unbounded
    if len(stack) != 1:
        raise PatternError("the pattern does not compile: missing ), unterminated subpattern")
    if unbounded_total > MAX_UNBOUNDED:
        raise PatternError(f"more than {MAX_UNBOUNDED} open-ended repeats (*, +, {{n,}})")


def validate_pattern(pattern: str) -> re.Pattern[str]:
    """The pattern compiled, case-insensitive, or a PatternError saying what is wrong."""
    text = pattern.strip()
    if not text:
        raise PatternError("the pattern is empty")
    if len(text) > MAX_PATTERN_LEN:
        raise PatternError(f"the pattern is longer than {MAX_PATTERN_LEN} characters")
    check_shape(text)
    try:
        compiled = re.compile(text, re.IGNORECASE)
    except re.error as exc:
        raise PatternError(f"the pattern does not compile: {exc}") from exc
    if compiled.search("") is not None:
        raise PatternError("the pattern matches empty text, so it would match every listing")
    return compiled


def clean_exclusions(words: list[str]) -> list[str]:
    """Trimmed, lower-cased, one of each, bounded in number and length; empty ones dropped."""
    seen: list[str] = []
    for word in words:
        line = " ".join(word.split()).lower()[:EXCLUSION_MAX].strip()
        if line and line not in seen:
            seen.append(line)
        if len(seen) >= MAX_EXCLUSIONS:
            break
    return seen


def exclusion_pattern(word: str) -> re.Pattern[str]:
    """The word or phrase as written, on word boundaries, any run of spaces between words."""
    parts = [re.escape(p) for p in word.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def price_of(text: str) -> float | None:
    """The first asking price the text states, in dollars; 0 for 'free'."""
    found = _PRICE.search(text)
    if found:
        whole = (found.group(1) or found.group(3)).replace(",", "")
        cents = found.group(2) or found.group(4) or ""
        return float(f"{whole}.{cents}" if cents else whole)
    if _FREE.search(text):
        return 0.0
    return None


def score_listing(
    text: str,
    compiled: re.Pattern[str] | None,
    exclusions: list[str],
    max_price: float | None,
) -> Score:
    """Where a listing stands before any model reads it: the words that rule it out, the price
    against the limit, and whether the pattern matches. Free, and done for every listing."""
    scan = text[:SCAN_MAX]
    hits: list[Hit] = []
    reasons: list[str] = []
    excluded: list[str] = []
    for word in exclusions:
        found = exclusion_pattern(word).search(scan)
        if found:
            excluded.append(word)
            hits.append(Hit("excluded", found.start(), found.end(), found.group(0)))
    matched: bool | None = None
    if compiled is not None:
        found = compiled.search(scan)
        matched = found is not None
        if found is not None and found.end() > found.start():
            hits.append(Hit("match", found.start(), found.end(), found.group(0)))
    price = price_of(scan)
    price_ok: bool | None = None
    if price is not None and max_price is not None and max_price > 0:
        price_ok = price <= max_price
    if excluded:
        reasons.append("says " + ", ".join(f'"{w}"' for w in excluded))
    if price_ok is False:
        reasons.append(f"asks ${price:g}, over the limit of ${max_price:g}")
    if excluded or price_ok is False:
        verdict = "no"
    elif matched:
        verdict = "fits"
        reasons.append("matches the pattern")
        if price_ok:
            reasons.append(f"${price:g} is within the limit")
        elif price is None:
            reasons.append("no price stated")
    else:
        verdict = "maybe"
        reasons.append(
            "does not match the pattern" if compiled is not None else "no pattern to match yet"
        )
    hits.sort(key=lambda h: (h.start, h.end))
    return Score(verdict, matched, hits, excluded, price, price_ok, reasons)


RANK = {"fits": 0, "maybe": 1, "no": 2}

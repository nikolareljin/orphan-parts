"""The search plan for a need: several phrasings a seller might have used, one match pattern
over listing text, and the words that rule a listing out. Marketplace has no public search API
and automating it is against its terms, so the plan is links the owner opens and a pattern the
app applies to the listings the owner brings back. Marketplace's own search box takes words,
not regular expressions.

The pattern and the exclusion words run on RE2, which matches in time linear in the text: no
pattern, however it is written, backtracks. The checks here are for the messages the owner
reads, not for safety: a bounded length, none of what RE2 does not have (lookarounds,
backreferences, ``\\C``), no comments and no inline flags but ``(?i)``, and counted repeats
kept small, since RE2's work per character grows with the size of the compiled pattern. The
text it runs over is bounded too."""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import re2

MAX_PATTERN_LEN = 300
# what a pattern may expand to: each atom counts one and a counted repeat {n,m} multiplies
# what it repeats by m; RE2's work per character of text grows with it
MAX_PATTERN_WEIGHT = 400
MAX_PHRASINGS = 6
MIN_PHRASINGS = 3
PHRASING_MAX = 120
WHY_MAX = 200
MAX_EXCLUSIONS = 20
EXCLUSION_MAX = 40
# the most of a listing that is kept, and that the pattern and the exclusions are run over
SCAN_MAX = 4000
# what rules a listing out unless the owner says otherwise
DEFAULT_EXCLUSIONS = ["for parts", "parts only", "broken", "not working", "does not work"]

# The price parsing runs on fixed patterns over at most SCAN_MAX characters. A dollar sign
# right after a letter is another dollar (CA$, AU$), except US$.
_PRICE = re.compile(
    r"(?:(?<![A-Za-z])|(?<![A-Za-z]US)(?<=US))\$\s?(\d{1,3}(?:,\d{3})+|\d{1,7})(?:\.(\d{1,2}))?"
    r"(k(?![a-z]))?"
    r"|\b(\d{1,3}(?:,\d{3})+|\d{1,7})(?:\.(\d{1,2}))?(k)?\s?(?:usd|dollars|bucks)\b",
    re.IGNORECASE,
)
# a number that goes on after a space in groups of three, as in "$1 200": not read as $1
_GROUP_AFTER = re.compile(r"[ \xa0\u202f]\d{3}(?!\w)")
_GROUP_BEFORE = re.compile(r"\d[ \xa0\u202f]$")
_FREE = re.compile(r"\bfree\b", re.IGNORECASE)
# "smoke-free", "pet free": free of something, not free to take
_FREE_OF = re.compile(
    r"(?:-|\b(?:smoke|pet|dust|hands|bpa|lead|rust|stain|odou?r|damage|scratch|crack|tax"
    r"|duty|hassle|worry|trouble|cruelty|gluten|latex|fragrance)\s+)$",
    re.IGNORECASE,
)
# "free shipping", "free home delivery", "free-standing": something else that is free
_FREE_WITH = re.compile(
    r"\s*(?:-\w|(?:local\s+|home\s+)?(?:shipping|delivery|returns?|gifts?)\b|home\b)",
    re.IGNORECASE,
)


class PatternError(ValueError):
    """The pattern cannot be used: it does not compile, is too long, or uses what is refused."""


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


def _options() -> Any:
    options = re2.Options()
    options.case_sensitive = False
    # a refused pattern is answered to the owner, not written to the server's log
    options.log_errors = False
    return options


_OPTIONS = _options()

_REFUSED_GROUPS = (
    ("(?=", "a lookahead such as (?=...) is not supported; match the words themselves"),
    ("(?!", "a negative lookahead such as (?!...) is not supported; use an exclusion word"),
    ("(?<=", "a lookbehind such as (?<=...) is not supported; match the words themselves"),
    ("(?<!", "a negative lookbehind such as (?<!...) is not supported; use an exclusion word"),
    ("(?P=", "backreferences are not supported"),
    ("(?#", "comments (?#...) are refused"),
)


def _count(pattern: str, i: int) -> tuple[int, int]:
    """The quantifier starting at ``i``, if any: (its length, the factor it multiplies what it
    repeats by). ``*``, ``+`` and ``?`` loop or skip and count one; ``{n,m}`` counts m, ``{n}``
    and ``{n,}`` count n. A lazy suffix is part of it."""
    if i >= len(pattern):
        return 0, 1
    ch = pattern[i]
    length, factor = 0, 1
    if ch in "*+?":
        length = 1
    elif ch == "{":
        found = re.match(r"\{(\d{1,6})(,?)(\d{0,6})\}", pattern[i:])
        if found is None:
            return 0, 1  # a literal brace
        low, comma, high = found.groups()
        length = found.end()
        factor = max(1, int(high) if comma and high else int(low))
    if length and pattern[i + length : i + length + 1] == "?":
        length += 1
    return length, factor


def check_pattern(pattern: str) -> None:
    """Raise PatternError, with a line the owner can act on, for what RE2 lacks or what is
    refused here: lookarounds, backreferences, ``\\C``, comments, inline flags other than
    ``(?i)``, and counted repeats that expand past MAX_PATTERN_WEIGHT. Whether the rest
    compiles is RE2's to say."""
    stack: list[int] = [0]  # the weight of each open group, the whole pattern at the bottom
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        weight = 1
        if ch == "\\":
            nxt = pattern[i + 1 : i + 2]
            if nxt in tuple("123456789") or nxt in ("k", "g"):
                raise PatternError("backreferences are not supported")
            if nxt == "C":
                raise PatternError("\\C (any byte) is refused; use . for any character")
            if nxt in ("p", "P", "x") and pattern[i + 2 : i + 3] == "{":
                close = pattern.find("}", i)
                i = n if close < 0 else close + 1
            elif nxt == "Q":
                close = pattern.find("\\E", i + 2)
                i = n if close < 0 else close + 2
            else:
                i += 2 if nxt not in ("p", "P") else 3
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1  # a ] first in the class is a literal
            while j < n and pattern[j] != "]":
                if pattern.startswith("[:", j):
                    close = pattern.find(":]", j + 2)
                    j = n if close < 0 else close + 2
                else:
                    j += 2 if pattern[j] == "\\" else 1
            i = j + 1
        elif ch == "(":
            if pattern.startswith("(?", i):
                for start, line in _REFUSED_GROUPS:
                    if pattern.startswith(start, i):
                        raise PatternError(line)
                if pattern.startswith("(?i)", i):
                    i += 4
                    continue
                named = re.match(r"\(\?P?<[A-Za-z_]", pattern[i:])
                if not pattern.startswith("(?:", i) and named is None:
                    raise PatternError(
                        "inline flags other than (?i) are refused; the pattern already"
                        " matches in any case"
                    )
            stack.append(0)
            i += 1
            continue
        elif ch == ")":
            if len(stack) == 1:
                raise PatternError("the pattern does not compile: unbalanced parenthesis")
            weight = max(1, stack.pop())
            i += 1
        elif ch in "|^$":
            i += 1
            continue
        else:
            i += 1
        length, factor = _count(pattern, i)
        i += length
        stack[-1] += weight * factor
        if stack[-1] > MAX_PATTERN_WEIGHT:
            raise PatternError(
                f"the counted repeats expand past {MAX_PATTERN_WEIGHT} steps ({{0,40}} counts"
                " 40, a group repeated {1,5} counts five times what is inside); use smaller"
                " counts, or + for an open-ended run"
            )


def compile_pattern(text: str) -> Any:
    """The pattern compiled by RE2, case-insensitive, or a PatternError with RE2's reason."""
    try:
        return re2.compile(text, _OPTIONS)
    except re2.error as exc:
        reason = exc.args[0] if exc.args else exc
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8", "replace")
        raise PatternError(f"the pattern does not compile: {reason}") from exc


def validate_pattern(pattern: str) -> Any:
    """The pattern compiled, case-insensitive, or a PatternError saying what is wrong."""
    text = pattern.strip()
    if not text:
        raise PatternError("the pattern is empty")
    if len(text) > MAX_PATTERN_LEN:
        raise PatternError(f"the pattern is longer than {MAX_PATTERN_LEN} characters")
    check_pattern(text)
    compiled = compile_pattern(text)
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


# a letter, a digit or an underscore in any script: what a word is made of
_WORD = r"\pL\pN\pM_"


@lru_cache(maxsize=512)
def exclusion_pattern(word: str) -> Any:
    """The word or phrase as written, any run of spaces between words, not inside another
    word; the phrase itself is group 1."""
    parts = [re2.escape(p) for p in word.split()]
    body = r"[\s\p{Z}]+".join(parts)
    return re2.compile(f"(?:^|[^{_WORD}])({body})(?:[^{_WORD}]|$)", _OPTIONS)


def _free(text: str) -> bool:
    """'free' said of the item: not "smoke-free", "pet free" or "free shipping"."""
    for found in _FREE.finditer(text):
        before = text[max(0, found.start() - 20) : found.start()]
        after = text[found.end() : found.end() + 30]
        if not _FREE_OF.search(before) and not _FREE_WITH.match(after):
            return True
    return False


def _amount(text: str, found: re.Match[str]) -> float | None:
    """One stated amount in dollars, or None when it is not guessed at."""
    if found.group(1) is not None:
        whole, cents, thousands = found.group(1), found.group(2), found.group(3)
        if _GROUP_AFTER.match(text, found.end(2) if cents else found.end(1)) and not thousands:
            return None
    else:
        whole, cents, thousands = found.group(4), found.group(5), found.group(6)
        if _GROUP_BEFORE.search(text, 0, found.start()):
            return None
    value = float(f"{whole.replace(',', '')}.{cents}" if cents else whole.replace(",", ""))
    return round(value * 1000, 2) if thousands else value


def amounts_in(text: str) -> list[float | None]:
    """Every dollar amount the text states, in order; None for one not guessed at."""
    return [_amount(text, found) for found in _PRICE.finditer(text)]


def price_of(text: str) -> float | None:
    """The asking price, in dollars: the first amount the text states, as a Marketplace listing
    puts the asking price first ("$20 (retail $50)" is 20, "$45 each or 2 for $80" is 45); a
    k after the number is thousands; 0 for 'free' when no number is given. A number that goes
    on in groups of three after a space ("$1 200") is not guessed at: None."""
    stated = amounts_in(text)
    if not stated:
        return 0.0 if _free(text) else None
    return stated[0]


def money(value: float) -> str:
    """Dollars as people write them: $1,200 or $9.50, never 1.2e+06."""
    return f"${value:,.0f}" if value == int(value) else f"${value:,.2f}"


def score_listing(
    text: str,
    compiled: Any,
    exclusions: list[str],
    max_price: float | None,
) -> Score:
    """Where a listing stands before any model reads it: the words that rule it out, the price
    against the limit (none when it is 0 or unset), and whether the pattern matches. Free, and
    done for every listing; RE2 keeps every search linear in the text."""
    scan = text[:SCAN_MAX]
    hits: list[Hit] = []
    reasons: list[str] = []
    excluded: list[str] = []
    for word in exclusions:
        found = exclusion_pattern(word).search(scan)
        if found:
            excluded.append(word)
            hits.append(Hit("excluded", found.start(1), found.end(1), found.group(1)))
    matched: bool | None = None
    if compiled is not None:
        found = compiled.search(scan)
        matched = found is not None
        if found is not None and found.end() > found.start():
            hits.append(Hit("match", found.start(), found.end(), found.group(0)))
    price = price_of(scan)
    price_ok: bool | None = None
    # several amounts on both sides of the limit ("$40, $10 off for pickup", "$20, retail
    # $50"): which one is asked is the owner's to read, so the price decides nothing
    mixed = False
    if price is not None and max_price is not None and max_price > 0:
        price_ok = price <= max_price
        others = {a for a in amounts_in(scan) if a is not None}
        if any((a <= max_price) != price_ok for a in others):
            mixed, price_ok = True, None
    if excluded:
        reasons.append("says " + ", ".join(f'"{w}"' for w in excluded))
    if price_ok is False and price is not None and max_price is not None:
        reasons.append(f"asks {money(price)}, over the limit of {money(max_price)}")
    if mixed:
        stated = sorted({a for a in amounts_in(scan) if a is not None})
        reasons.append(
            "states several prices (" + ", ".join(money(a) for a in stated) + "), some over"
            f" the limit of {money(max_price or 0)}; check which one is asked"
        )
    if excluded or price_ok is False:
        verdict = "no"
    elif mixed:
        verdict = "maybe"
        if compiled is not None:
            reasons.append("matches the pattern" if matched else "does not match the pattern")
    elif matched:
        verdict = "fits"
        reasons.append("matches the pattern")
        if price_ok and price is not None:
            reasons.append(f"{money(price)} is within the limit")
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

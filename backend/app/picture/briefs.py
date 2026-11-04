"""Corrections written into the demo set file, line by line, so its comments and its order
stay as they are: an item's ``picture_brief`` or ``reuse_picture_brief`` beside its other
keys, a project's under ``propose: corrections:``. A value already there is replaced."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

ITEM_KEYS = ("picture_brief", "reuse_picture_brief")


@dataclass(frozen=True)
class SetBrief:
    """Where a brief goes: an item's key and field, or a project correction's key."""

    brief: str
    item: str = ""
    field: str = ""
    correction: str = ""


def _quoted(text: str) -> str:
    # a JSON string is a YAML double-quoted scalar: any character is safe in it
    return json.dumps(" ".join(text.split()), ensure_ascii=False)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _item_block(lines: list[str], key: str) -> tuple[int, int]:
    """The lines of the item ``- key: <key>``: its first line and the line after its last."""
    pattern = re.compile(rf"^(\s*)- key:\s*{re.escape(key)}\s*$")
    for start, line in enumerate(lines):
        found = pattern.match(line)
        if not found:
            continue
        dash = len(found.group(1))
        end = start + 1
        while end < len(lines):
            text = lines[end]
            if text.strip() and not text.lstrip().startswith("#") and _indent(text) <= dash:
                break
            end += 1
        # trailing blank lines and comments belong to what follows
        while end > start + 1 and (
            not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")
        ):
            end -= 1
        return start, end
    raise KeyError(f"no item {key!r} in the set")


def _set_item(lines: list[str], key: str, field: str, brief: str) -> None:
    if field not in ITEM_KEYS:
        raise ValueError(f"{field!r} is not a brief an item takes")
    start, end = _item_block(lines, key)
    inner = _indent(lines[start]) + 2
    entry = f"{' ' * inner}{field}: {_quoted(brief)}"
    for n in range(start + 1, end):
        if re.match(rf"^\s*{field}:", lines[n]):
            lines[n] = entry
            return
    # after the key it corrects (picture: or reuse_picture:), else at the end of the item
    anchor = "picture" if field == "picture_brief" else "reuse_picture"
    for n in range(start + 1, end):
        if re.match(rf"^\s*{anchor}:", lines[n]):
            lines.insert(n + 1, entry)
            return
    lines.insert(end, entry)


def _section(lines: list[str], name: str, indent: int, start: int = 0) -> int:
    pattern = re.compile(rf"^{' ' * indent}{name}:\s*(#.*)?$")
    for n in range(start, len(lines)):
        if pattern.match(lines[n]):
            return n
    return -1


def _block_end(lines: list[str], start: int) -> int:
    level = _indent(lines[start])
    end = start + 1
    while end < len(lines):
        text = lines[end]
        if text.strip() and not text.lstrip().startswith("#") and _indent(text) <= level:
            break
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def _set_correction(lines: list[str], key: str, brief: str) -> None:
    propose = _section(lines, "propose", 0)
    if propose < 0:
        raise KeyError("the set has no propose: section")
    corrections = _section(lines, "corrections", 2, propose)
    entry = f"    {_quoted(key)}: {_quoted(brief)}"
    if corrections < 0:
        end = _block_end(lines, propose)
        lines[end:end] = ["  corrections:", entry]
        return
    end = _block_end(lines, corrections)
    quoted = _quoted(key)
    for n in range(corrections + 1, end):
        stripped = lines[n].strip()
        if stripped.startswith(f"{quoted}:") or stripped.startswith(f"{key}:"):
            lines[n] = entry
            return
    lines.insert(end, entry)


def apply(text: str, briefs: list[SetBrief]) -> str:
    """The set file's text with each brief written in; everything else as it was."""
    lines = text.splitlines()
    for b in briefs:
        if b.item:
            _set_item(lines, b.item, b.field, b.brief)
        elif b.correction:
            _set_correction(lines, b.correction, b.brief)
        else:
            raise ValueError("a brief names an item or a project correction")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

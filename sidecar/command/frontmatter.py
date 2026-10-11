"""Frontmatter: reading every key, writing only Command's own (design §3.4).

Reading parses the YAML block with PyYAML's safe loader. Writing never
re-serialises the block: it replaces the lines of one top-level key and
leaves every other byte — other keys, comments, quoting, the fences, the
body — as it was. Each write is parsed back before it's accepted: the key
must hold exactly what was written and every other key must be unchanged,
so a malformed result never reaches the disk.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

import yaml

from .vault import Invalid

_OPEN = re.compile(r"\A(\ufeff?)---[ \t]*(\r?\n)")
_CLOSE = re.compile(r"(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)")


class FrontmatterError(Invalid):
    pass


@dataclass
class Parts:
    bom: str
    newline: str
    open: str  # the opening fence line, newline included
    block: str | None  # the YAML between the fences; None when there's no frontmatter
    close: str  # the closing fence line, newline included when there is one
    body: str


def split(text: str) -> Parts:
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    fallback_nl = "\r\n" if "\r\n" in text else "\n"
    m = _OPEN.match(text)
    if m:
        pos = m.end()
        while pos <= len(text):
            close = _CLOSE.match(text, pos)
            if close:
                return Parts(bom, m.group(2), text[len(bom):m.end()], text[m.end():pos],
                             close.group(0), text[close.end():])
            nxt = text.find("\n", pos)
            if nxt < 0:
                break
            pos = nxt + 1
    # No fences, or an opening fence never closed: not frontmatter.
    return Parts(bom, fallback_nl, "", None, "", text[len(bom):])


def _parse(block: str | None) -> dict:
    if block is None or not block.strip():
        return {}
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        raise FrontmatterError(f"The frontmatter isn't valid YAML: {e}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FrontmatterError("The frontmatter isn't a set of keys")
    return data


def load(text: str) -> dict:
    """Every key, or FrontmatterError when the block doesn't parse."""
    return _parse(split(text).block)


def load_lenient(text: str) -> dict:
    """Every key, or nothing when the block doesn't parse — for reading a
    whole campaign, where one broken note mustn't hide the rest."""
    try:
        return load(text)
    except FrontmatterError:
        return {}


# ---------------------------------------------------------------------------
# Values Command reads
# ---------------------------------------------------------------------------

_LINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")


def link_target(entry) -> str:
    """The note a list entry names: the target of a `[[link]]` (no alias,
    heading, folder or .md), or a plain string as written. An unquoted
    `- [[Name]]` reaches YAML as a nested list and is read the same way."""
    if isinstance(entry, list) and len(entry) == 1 and isinstance(entry[0], list) and len(entry[0]) == 1:
        entry = f"[[{entry[0][0]}]]"
    text = str(entry).strip()
    m = _LINK.search(text)
    if m:
        text = re.split(r"\\?\||#", m.group(1))[0].strip()
    return text.split("/")[-1].removesuffix(".md").strip()


def entry_text(entry) -> str:
    """An entry as the string Command writes back."""
    if isinstance(entry, str):
        return entry
    return f"[[{link_target(entry)}]]"


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def spent_value(value) -> str | None:
    """`spent` as shown: its date, or "yes" for a bare true. False, null and
    an empty value are unspent."""
    if value is None or value is False or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is True:
        return "yes"
    return str(value)


def date_value(value) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None if value is None else str(value)


# ---------------------------------------------------------------------------
# Writing one key
# ---------------------------------------------------------------------------

def _render(key: str, value, nl: str) -> list[str]:
    if isinstance(value, (date, datetime)):
        return [f"{key}: {date_value(value)}{nl}"]
    if isinstance(value, list):
        if not value:
            return [f"{key}: []{nl}"]
        # Obsidian's own shape for a list property: block items, two-space
        # indent, double-quoted (a bare [[link]] would parse as a nested list).
        return [f"{key}:{nl}"] + [f"  - {json.dumps(str(v), ensure_ascii=False)}{nl}" for v in value]
    return [f"{key}: {json.dumps(str(value), ensure_ascii=False)}{nl}"]


def _region(lines: list[str], key: str) -> tuple[int, int] | None:
    """The lines holding top-level `key`: its own line plus what belongs to
    it (indented lines, or `-` items at column 0). Blank lines between are
    kept with it; trailing ones aren't."""
    head = re.compile(rf"{re.escape(key)}[ \t]*:(?:[ \t]|\r?\n|\Z)")
    for i, line in enumerate(lines):
        if head.match(line):
            end = i + 1
            j = i + 1
            while j < len(lines):
                line_j = lines[j]
                if not line_j.strip():
                    j += 1
                    continue
                if line_j[0] in " \t" or line_j.startswith("-"):
                    j += 1
                    end = j
                    continue
                break
            return i, end
    return None


def _expected(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, list):
        return [str(v) for v in value]
    return value


def set_key(text: str, key: str, value) -> str:
    """`text` with top-level `key` set to `value` (a date, a string or a list
    of strings), or removed when `value` is None. Only that key's lines
    change. Refuses (FrontmatterError) when the frontmatter doesn't parse, or
    when the result wouldn't read back as intended."""
    parts = split(text)
    before = _parse(parts.block)
    if value is None and key not in before:
        return text

    lines = (parts.block or "").splitlines(keepends=True)
    rendered = [] if value is None else _render(key, value, parts.newline)
    region = _region(lines, key)
    if region is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += parts.newline
        lines += rendered
    else:
        lines[region[0]:region[1]] = rendered
    block = "".join(lines)

    if parts.block is None:
        result = f"{parts.bom}---{parts.newline}{block}---{parts.newline}{parts.body}"
    elif not block.strip():
        result = parts.bom + parts.body
    else:
        result = parts.bom + parts.open + block + parts.close + parts.body

    after = load(result)
    others_before = {k: v for k, v in before.items() if k != key}
    others_after = {k: v for k, v in after.items() if k != key}
    written_ok = (key not in after) if value is None else (after.get(key) == _expected(value))
    if not written_ok or others_before != others_after:
        raise FrontmatterError(
            f"Couldn't write {key!r} without disturbing the rest of the frontmatter "
            "(a duplicate key, or a layout Command doesn't recognise)"
        )
    return result

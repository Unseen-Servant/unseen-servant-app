"""Foresight's encounters (docs/roadmap/2026-11-03-foresight-design.md §3).

An encounter is a note whose frontmatter has ``round``; Foresight owns
``round`` and ``turn``, the name of the row whose turn it is. The first table
in the body is the tracker: its header row is the column list, its first
column holds the rows' names, a name struck through (``~~Goblin 1~~``) is out
of the fight, and a link's alias names a second row from the same note
(``[[Goblin\\|Goblin 2]]``, the pipe escaped as a table needs). Text around
the table is the GM's and is never touched.

Reading is lenient: cells past the header's are kept as written, and a link
written with a bare pipe is read whole. Writing follows Command's discipline
(design §3.5): hash-checked against the version the caller read, atomic, the
frontmatter set key by key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import frontmatter as fm
from . import vault

# Where a new encounter goes, and what it's called (`Encounter N`), as
# sessions are numbered.
TRACK = "Encounters"
NAME = "Encounter"

_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_DELIMITER = re.compile(r"\s*(:?)-+(:?)\s*")
_LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")


@dataclass
class Row:
    name: str
    link: str | None = None  # the note it links to, as the link spells it
    out: bool = False
    cells: list[str] = field(default_factory=list)


@dataclass
class _Table:
    start: int  # the header's line in the body
    end: int  # the line after the last row
    columns: list[str]
    aligns: list[str]  # each column's delimiter ends: "", ":-", "-:" or ":-:"
    rows: list[Row]
    extra: dict[str, list[str]]  # a row's cells past the header's, by name


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _cells(line: str) -> list[str]:
    """A table line's cells: split on its pipes, but not an escaped one or
    one inside a ``[[link]]``. The outer pipes are optional."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells: list[str] = []
    cur: list[str] = []
    depth = i = 0
    while i < len(s):
        if s.startswith("\\|", i):
            cur.append("\\|")
            i += 2
        elif s.startswith("[[", i):
            depth += 1
            cur.append("[[")
            i += 2
        elif s.startswith("]]", i) and depth:
            depth -= 1
            cur.append("]]")
            i += 2
        elif s[i] == "|" and not depth:
            cells.append("".join(cur).strip())
            cur = []
            i += 1
        else:
            cur.append(s[i])
            i += 1
    cells.append("".join(cur).strip())
    return cells


def _unescape(cell: str) -> str:
    return cell.replace("\\|", "|")


def _shown(link: str) -> str:
    """What a link with no alias shows: its note's name, without folders,
    heading or ``.md``."""
    target = re.split(r"[#^]", link, maxsplit=1)[0]
    return PurePosixPath(target.strip()).name.removesuffix(".md")


def _row(cells: list[str], width: int) -> tuple[Row, list[str]]:
    """A table line's row, and its cells past the header's ``width``."""
    name = cells[0]
    out = len(name) > 4 and name.startswith("~~") and name.endswith("~~")
    if out:
        name = name[2:-2].strip()
    link = None
    m = _LINK.fullmatch(name)
    if m:
        target, *alias = re.split(r"\\?\|", m.group(1), maxsplit=1)
        link = target.strip()
        name = alias[0].strip() if alias and alias[0].strip() else _shown(link)
    else:
        name = _unescape(name)
    rest = [_unescape(c) for c in cells[1:]]
    cells_in = (rest + [""] * width)[: width - 1]
    return Row(name, link, out, cells_in), cells[width:]


def _find(lines: list[str]) -> _Table | None:
    """The body's first table: a header line, then a delimiter line with as
    many cells, then the rows up to a blank line or one without a pipe.
    Fenced and indented code is passed over."""
    fence: str | None = None
    for i, line in enumerate(lines):
        opened = _FENCE.match(line)
        if fence is not None:
            if opened and opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence):
                fence = None
            continue
        if opened:
            fence = opened.group(1)
            continue
        if "|" not in line or line.startswith(("    ", "\t")) or i + 1 >= len(lines):
            continue
        columns = _cells(line)
        delimiters = _cells(lines[i + 1])
        if len(delimiters) != len(columns) or "|" not in lines[i + 1]:
            continue
        ends = [_DELIMITER.fullmatch(d) for d in delimiters]
        if not all(ends):
            continue
        end = i + 2
        while end < len(lines) and lines[end].strip() and "|" in lines[end]:
            end += 1
        rows, extra = [], {}
        for raw in lines[i + 2:end]:
            row, past = _row(_cells(raw), len(columns))
            rows.append(row)
            if past:
                extra[row.name.casefold()] = past
        aligns = [(e.group(1) + "-" + e.group(2)) if e.group(1) or e.group(2) else "" for e in ends]
        return _Table(i, end, [_unescape(c) for c in columns], aligns, rows, extra)
    return None


def _round(value) -> int:
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return max(1, value)
    if isinstance(value, str) and value.strip().isdigit():
        return max(1, int(value))
    return 1


def _turn(value, rows: list[Row]) -> str | None:
    """The row whose turn it is: the one ``turn`` names, else the first in
    the fight, else none."""
    if isinstance(value, str):
        named = next((r for r in rows if r.name.casefold() == value.strip().casefold()), None)
        if named is not None:
            return named.name
    first = next((r for r in rows if not r.out), None)
    return first.name if first else None


def is_encounter(meta: dict) -> bool:
    return "round" in meta


def read(campaign: Path, rel: str) -> dict:
    """The encounter at ``rel``: its rows, columns, round and turn, the hash
    a save is checked against, and whether it's spent."""
    note = vault.read_note(campaign, rel)
    meta = fm.load(note["content"])
    if not is_encounter(meta):
        raise vault.Invalid(f"{note['name']!r} isn't an encounter: its frontmatter has no round")
    body = fm.split(note["content"]).body
    table = _find(body.splitlines(keepends=True))
    rows = table.rows if table else []
    return {
        "path": note["path"],
        "name": note["name"],
        "hash": note["hash"],
        "spent": fm.spent_value(meta.get("spent")),
        "round": _round(meta.get("round")),
        "turn": _turn(meta.get("turn"), rows),
        "columns": table.columns if table else [],
        "rows": [{"name": r.name, "link": r.link, "out": r.out, "cells": r.cells} for r in rows],
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _escape(cell: str) -> str:
    return " ".join(cell.split()).replace("|", "\\|")


def _name_cell(row: Row) -> str:
    if row.link:
        name = _escape(row.name)
        text = f"[[{row.link}]]" if row.name == _shown(row.link) else f"[[{row.link}\\|{name}]]"
    else:
        text = _escape(row.name)
    return f"~~{text}~~" if row.out else text


def _render(columns: list[str], aligns: list[str], rows: list[Row], extra: dict[str, list[str]], nl: str) -> list[str]:
    """The table as written: each column padded to its widest cell, so it
    reads as a table in any text editor too."""
    width = len(columns)
    grid = [[_escape(c) for c in columns]]
    for row in rows:
        cells = [_escape(c) for c in (row.cells + [""] * width)[: width - 1]]
        grid.append([_name_cell(row), *cells, *extra.get(row.name.casefold(), [])])
    widths = [max(3, *(len(line[c]) for line in grid if c < len(line))) for c in range(max(map(len, grid)))]

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + f" |{nl}"

    def rule(i: int) -> str:
        """A column's delimiter, as wide as its cells and their spaces, its
        alignment colons kept at its ends."""
        a = aligns[i] if i < len(aligns) else ""
        dashes = "-" * (widths[i] + 2)
        if a.startswith(":"):
            dashes = ":" + dashes[1:]
        if a.endswith(":"):
            dashes = dashes[:-1] + ":"
        return dashes

    head = [line(grid[0]), "|" + "|".join(rule(i) for i in range(width)) + f"|{nl}"]
    return head + [line(cells) for cells in grid[1:]]


def _check(columns: list[str], rows: list[Row], turn: str | None) -> None:
    if not columns or not columns[0].strip():
        raise vault.Invalid("An encounter's table needs its first column, the rows' names")
    seen: set[str] = set()
    for row in rows:
        key = row.name.strip().casefold()
        if not key:
            raise vault.Invalid("A row needs a name")
        if key in seen:
            raise vault.Invalid(f"Two rows are named {row.name!r}: a row's name is unique in its encounter")
        seen.add(key)
    if turn is not None and turn.casefold() not in seen:
        raise vault.Invalid(f"No row named {turn!r} to have the turn")


def _with_table(text: str, columns: list[str], rows: list[Row]) -> str:
    """``text`` with its first table rewritten, or the table added at the end
    of the body when it has none. Nothing else in the body changes."""
    parts = fm.split(text)
    head = text[: len(text) - len(parts.body)]
    lines = parts.body.splitlines(keepends=True)
    table = _find(lines)
    if table is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += parts.newline
        if lines and lines[-1].strip():
            lines.append(parts.newline)
        return head + "".join(lines + _render(columns, [], rows, {}, parts.newline))
    rendered = _render(columns, table.aligns, rows, table.extra, parts.newline)
    if table.end == len(lines) and not lines[-1].endswith(("\n", "\r")):
        rendered[-1] = rendered[-1].rstrip("\r\n")
    return head + "".join(lines[: table.start] + rendered + lines[table.end:])


def save(
    campaign: Path,
    rel: str,
    base_hash: str,
    round_: int,
    turn: str | None,
    columns: list[str],
    rows: list[Row],
) -> str:
    """Write the encounter back over the note at ``rel`` if it's still the
    version the caller read (``base_hash``): its table, ``round`` and
    ``turn``. The new hash."""
    note = vault.read_note(campaign, rel)
    if note["hash"] != base_hash:
        raise vault.Conflict(f"{rel!r} changed on disk", current_hash=note["hash"])
    if not is_encounter(fm.load(note["content"])):
        raise vault.Invalid(f"{note['name']!r} isn't an encounter: its frontmatter has no round")
    _check(columns, rows, turn)
    text = _with_table(note["content"], columns, rows)
    text = fm.set_key(text, "round", max(1, round_))
    text = fm.set_key(text, "turn", turn)
    if text == note["content"]:
        return base_hash
    return vault.write_note(campaign, rel, text, base_hash)


def _folder(campaign: Path) -> str:
    """The Encounters track as it is on disk, made a note track the first
    time it's needed."""
    for p in campaign.iterdir():
        if p.is_dir() and p.name.casefold() == TRACK.casefold():
            return p.name
    vault.create_track(campaign, TRACK)
    vault.save_track_kind(campaign, TRACK, "note")
    return TRACK


def next_name(campaign: Path) -> str:
    """`Encounter N`, N one more than the highest in a note's name of that
    shape, and free."""
    taken = {n["name"].casefold() for n in vault.scan(campaign)["notes"]}
    numbers = [int(m.group(1)) for name in taken if (m := re.fullmatch(rf"{NAME.casefold()} (\d+)", name))]
    n = max(numbers, default=0) + 1
    while f"{NAME} {n}".casefold() in taken:
        n += 1
    return f"{NAME} {n}"


def create(campaign: Path, columns: list[str], rows: list[Row]) -> dict:
    """A new encounter in the Encounters track holding ``rows``, at round 1
    with the turn on its first row in the fight."""
    first = next((r for r in rows if not r.out), None)
    turn = first.name if first else None
    _check(columns, rows, turn)
    rel = vault.create_note(campaign, _folder(campaign), next_name(campaign))
    text = fm.set_key("", "round", 1)
    text = fm.set_key(text, "turn", turn)
    text = _with_table(text, columns, rows)
    vault.atomic_write(campaign / rel, text.encode("utf-8"))
    return read(campaign, rel)

"""Linearize Markdown pipe-tables into per-row sentences.

For a chunk with chunk_type == "table":
  1. Split into pipe-table lines.
  2. Identify the header row (first non-separator row, treated as field
     names).
  3. For each subsequent data row, build a sentence of the form:
       "<header_1>: <cell_1>; <header_2>: <cell_2>; ..."
     skipping empty cells. Strip Markdown emphasis (** **) from cells.
  4. Skip rows that are entirely empty or are clearly continuation rows
     of a multi-line cell.

Source-of-truth: vendored verbatim from table_retrieval_spike's
linearize_tables.py (sister experiments repo, verdict 2026-04-27).
The TTRPG title-row heuristic in `_parse_table` (single-cell title row
before separator → demote, take first post-separator row as header) is
load-bearing for the BFRPG armor / weapons family of tables.

Edge cases handled:
  - Tables with multiple `---` separator rows: take the first row
    before any `---` as the header.
  - Tables with no separator row: take the first row as the header
    unconditionally.
  - Tables where the header itself spans multiple rows: fall back to
    positional column names ("col1", "col2", ...).
  - Cells containing `<br>` or `\\n` breaks: replaced with spaces.
  - Tables that aren't pipe-tables (chunk_type=="table" but no `|` —
    rare): return ([], []) so callers can fall back to atomic embedding.
"""
from __future__ import annotations

import re

_EMPHASIS_RE = re.compile(r"\*+([^*]+)\*+")
_SEPARATOR_RE = re.compile(r"^\s*\|?\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?\s*$")


def _strip_emphasis(s: str) -> str:
    return _EMPHASIS_RE.sub(r"\1", s).strip()


def _split_pipe_row(line: str) -> list[str] | None:
    """Split a markdown pipe-table row. Returns None if not a pipe row.

    Handles leading/trailing pipes by stripping. Treats `<br>` / `\\n`
    inside a cell as a soft break (replaced with space).
    """
    line = line.strip()
    if not line.startswith("|") and "|" not in line:
        return None
    s = line.strip().strip("|")
    cells = [c.strip().replace("<br>", " ").replace("\n", " ") for c in s.split("|")]
    return cells


def _is_empty_row(cells: list[str]) -> bool:
    return all(not _strip_emphasis(c) for c in cells)


def _parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse a pipe-table chunk into (header, data_rows).

    Returns ([], []) if no parseable table found.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if _SEPARATOR_RE.match(line):
            rows.append(["__SEP__"])
            continue
        cells = _split_pipe_row(line)
        if cells is None:
            continue
        rows.append(cells)

    if not rows:
        return [], []

    sep_idx = None
    for i, r in enumerate(rows):
        if r == ["__SEP__"]:
            sep_idx = i
            break

    def _non_empty_count(r: list[str]) -> int:
        return sum(1 for c in r if _strip_emphasis(c))

    if sep_idx is not None:
        # Header is normally the row immediately before the separator. But
        # some tables (BFRPG armor) put a single-cell title row there,
        # putting the real header AFTER the separator. Detect this: if the
        # candidate header has < 2 non-empty cells AND subsequent rows
        # have >= 2, demote it to a title and use the first post-separator
        # row instead.
        header_idx = sep_idx - 1
        if header_idx < 0:
            return [], []
        candidate = rows[header_idx]
        post_sep = [r for r in rows[sep_idx + 1:] if r != ["__SEP__"] and not _is_empty_row(r)]
        post_sep_max = max((_non_empty_count(r) for r in post_sep), default=0)
        if _non_empty_count(candidate) < 2 and post_sep_max >= 2 and post_sep:
            header = post_sep[0]
            data_start = rows.index(post_sep[0]) + 1
        else:
            header = candidate
            data_start = sep_idx + 1
    else:
        header = rows[0]
        data_start = 1

    if not header or _is_empty_row(header):
        return [], []

    data: list[list[str]] = []
    for r in rows[data_start:]:
        if r == ["__SEP__"]:
            continue
        if _is_empty_row(r):
            continue
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        elif len(r) > len(header):
            r = r[: len(header)]
        data.append(r)

    return [_strip_emphasis(c) for c in header], [[_strip_emphasis(c) for c in r] for r in data]


def linearize_table(chunk_text: str) -> tuple[list[str], list[str]]:
    """Returns (header, [row_sentence, ...]).

    Row sentence format: "<header_1>: <cell_1>; <header_2>: <cell_2>; ..."
    Cells with empty header or empty value are skipped (cell-by-cell).
    """
    header, data = _parse_table(chunk_text)
    if not header:
        return [], []

    if all(not h for h in header):
        header = [f"col{i+1}" for i in range(len(header))]
    else:
        header = [h if h else f"col{i+1}" for i, h in enumerate(header)]

    sentences: list[str] = []
    for row in data:
        parts: list[str] = []
        for h, v in zip(header, row):
            v = v.strip()
            if not v:
                continue
            parts.append(f"{h}: {v}")
        if parts:
            sentences.append("; ".join(parts))
    return header, sentences

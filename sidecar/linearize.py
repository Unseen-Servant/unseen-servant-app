"""Linearize Markdown pipe-tables into per-row sentences for embedding.

Ported from table_retrieval_spike/linearize_tables.py (verdict
2026-04-27: +0.152 MRR@5 on table queries, zero regressions). For a
chunk with chunk_type == "table":

  1. Split into pipe-table lines.
  2. Identify the header row (last non-empty row before the first
     ``---`` separator; first row if no separator).
  3. For each data row, build a sentence of the form:
       "<header_1>: <cell_1>; <header_2>: <cell_2>; ..."
     skipping empty cells. Markdown emphasis (** **) is stripped.

Edge cases handled (all spike-verified):
  - Title-row prefix (BFRPG armor tables): a row with < 2 non-empty
    cells before the separator is a *title*, not the header — the real
    header is the first post-separator row. Load-bearing: without it,
    row sentences silently drop most columns.
  - Empty header cells: replaced with positional names ("col2") so
    data is never dropped.
  - ``<br>`` / newlines inside cells: flattened to spaces.
  - Rows narrower/wider than the header: padded / truncated to width.
  - Non-pipe text: returns ([], []) — the caller falls back to the
    atomic embed unit.
"""
from __future__ import annotations

import re


_EMPHASIS_RE = re.compile(r"\*+([^*]+)\*+")
_SEPARATOR_RE = re.compile(r"^\s*\|?\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?\s*$")


def _strip_emphasis(s: str) -> str:
    return _EMPHASIS_RE.sub(r"\1", s).strip()


def _split_pipe_row(line: str) -> list[str] | None:
    """Split a markdown pipe-table row. Returns None if not a pipe row.

    Handles leading/trailing pipes by stripping. Treats ``<br>`` /
    newlines inside a cell as a soft break (replaced with space).
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
            # Mark separator with a sentinel so we know where the header ends.
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
        # No separator — take first non-empty row as header.
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
    """Returns (header, [row_sentence, ...]); ([], []) if unparseable.

    Row sentence format: "<header_1>: <cell_1>; <header_2>: <cell_2>; ..."
    Cells with empty value are skipped (cell-by-cell).
    """
    header, data = _parse_table(chunk_text)
    if not header:
        return [], []

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


_WS_RE = re.compile(r"\s+")


def _content_len(s: str) -> int:
    return len(_WS_RE.sub("", s))


def coverage_ratio(chunk_text: str, header: list[str], sentences: list[str]) -> float:
    """Rough fraction of the table's cell content represented in the row
    sentences. A tripwire for lossy parses (e.g. data rows truncated to a
    too-narrow detected header), not a precise metric.

    Denominator: content chars of every pipe-row cell in the source,
    plus the header labels repeated once per additional sentence (labels
    appear in every sentence, so without this term long tables would
    inflate the ratio and mask dropped columns).
    """
    src = 0
    for line in chunk_text.splitlines():
        if _SEPARATOR_RE.match(line):
            continue
        cells = _split_pipe_row(line)
        if cells is None:
            continue
        src += sum(_content_len(_strip_emphasis(c)) for c in cells)
    if src == 0 or not sentences:
        return 0.0
    label_chars = sum(_content_len(h) for h in header)
    denom = src + label_chars * (len(sentences) - 1)
    emitted = sum(_content_len(s) for s in sentences)
    return emitted / denom

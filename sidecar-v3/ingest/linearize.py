"""F (embed units). Small units — what actually gets a vector (plan §3.2 F).

Prose chunks split into ~400-char units at word boundaries (no overlap, no
mid-word). Table chunks (pipe-cell rows from Stage B) reformat each data row into
a "<header>: <cell>; …" sentence — the +0.152 MRR table win, ported from v2's
linearize.py (constitution #7: copied, not imported) — pointing every row unit at
the same parent. A lossy parse (coverage_ratio < COVERAGE_MIN) or a non-pipe
table falls back to the per-row atomic unit, so this never does worse than the
rung-2 baseline. Every unit inherits its chunk's section/page/bbox/lang.
"""
from __future__ import annotations

import re

from domain.models import Chunk, ChunkKind, Unit

UNIT_CAP = 400       # chars per prose unit
COVERAGE_MIN = 0.6   # below this, a parsed table is lossy → fall back to bare rows

_EMPHASIS_RE = re.compile(r"\*+([^*]+)\*+")
_WS_RE = re.compile(r"\s+")


def _split_prose(text: str, cap: int) -> list[str]:
    parts: list[str] = []
    cur = ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > cap:
            parts.append(cur)
            cur = w
        else:
            cur = w if not cur else f"{cur} {w}"
    if cur:
        parts.append(cur)
    return parts or [""]


# ---- pipe-cell table linearization (ported from v2 sidecar/linearize.py) ----

def _strip_emphasis(s: str) -> str:
    return _EMPHASIS_RE.sub(r"\1", s).strip()


def _split_pipe_row(line: str) -> list[str] | None:
    """Split a pipe-cell row → cells; None if the line has no cell delimiter.
    A single-cell line (a table title with no pipe) returns None and is skipped."""
    line = line.strip()
    if "|" not in line:
        return None
    return [c.strip().replace("\n", " ") for c in line.strip("|").split("|")]


def _is_empty_row(cells: list[str]) -> bool:
    return all(not _strip_emphasis(c) for c in cells)


def _parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse a pipe-cell table → (header, data_rows); ([], []) if none. v3 has no
    Markdown separator, so the first pipe row is the header (single-cell title
    rows have no pipe and are skipped by _split_pipe_row)."""
    rows = [c for line in text.splitlines() if line.strip()
            if (c := _split_pipe_row(line)) is not None]
    if not rows or _is_empty_row(rows[0]):
        return [], []
    header, data_rows = rows[0], rows[1:]
    data: list[list[str]] = []
    for r in data_rows:
        if _is_empty_row(r):
            continue
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        elif len(r) > len(header):
            r = r[: len(header)]
        data.append(r)
    return [_strip_emphasis(c) for c in header], [[_strip_emphasis(c) for c in r] for r in data]


def linearize_table(chunk_text: str) -> tuple[list[str], list[str]]:
    """(header, [row_sentence, …]); ([], []) if unparseable. Row sentence:
    "<h1>: <c1>; <h2>: <c2>; …" — empty cells skipped, empty headers → colN."""
    header, data = _parse_table(chunk_text)
    if not header:
        return [], []
    header = [h if h else f"col{i+1}" for i, h in enumerate(header)]
    sentences: list[str] = []
    for row in data:
        parts = [f"{h}: {v.strip()}" for h, v in zip(header, row) if v.strip()]
        if parts:
            sentences.append("; ".join(parts))
    return header, sentences


def _content_len(s: str) -> int:
    return len(_WS_RE.sub("", s))


def coverage_ratio(chunk_text: str, header: list[str], sentences: list[str]) -> float:
    """Fraction of the table's cell content represented in the row sentences — a
    tripwire for lossy parses (data truncated to a too-narrow header)."""
    src = 0
    for line in chunk_text.splitlines():
        cells = _split_pipe_row(line)
        if cells is None:
            continue
        src += sum(_content_len(_strip_emphasis(c)) for c in cells if _strip_emphasis(c))
    if src == 0 or not sentences:
        return 0.0
    label_chars = sum(_content_len(h) for h in header)
    denom = src + label_chars * (len(sentences) - 1)
    return sum(_content_len(s) for s in sentences) / denom


def _table_texts(chunk_text: str) -> list[str]:
    """Row sentences if the table parses faithfully, else bare per-row fallback."""
    header, sentences = linearize_table(chunk_text)
    if sentences and coverage_ratio(chunk_text, header, sentences) >= COVERAGE_MIN:
        return sentences
    return [r.strip() for r in chunk_text.split("\n") if r.strip()]


def to_units(chunk: Chunk) -> tuple[Unit, ...]:
    texts = _table_texts(chunk.text) if chunk.kind is ChunkKind.table else _split_prose(chunk.text, UNIT_CAP)
    return tuple(
        Unit(
            id=f"{chunk.id}:u{i}",
            chunk_id=chunk.id,
            text=t,
            kind=chunk.kind,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            bbox_spans=chunk.bbox_spans,
            lang=chunk.lang,
        )
        for i, t in enumerate(texts)
    )

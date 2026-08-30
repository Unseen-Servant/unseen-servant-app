"""Aggregation: atomic text runs with geometry into a block hierarchy.

PDF has no block primitive. MuPDF synthesizes blocks in stext-device.c by
clustering characters into lines on baseline continuity and lines into blocks on
flow proximity; PyMuPDF exposes that heuristic, and W1 depends on it. This
module owns the equivalent aggregation for a permissively licensed backend.

Its input unit is one atomic run — a PDFium text object. Task 3 measured that
such an object never spans two table columns, so this module only ever merges
runs upward into words and cells; it never splits one. Splitting a run on gap
width is what collapses a table row into a single line.

Imports no PDF library — the run source is swappable without touching this.
"""
from __future__ import annotations

import statistics
from typing import Sequence

from domain.models import BBox
from ingest.raw import Span, TextBlock, TextLine, norm_ws

# Tunable constants, expressed as multiples of the row's em (its type size) so
# they scale with the page instead of assuming one. Per the plan's
# anti-overfitting rule these may be tuned ONLY against the ten section 4.3
# fixture pages; the 40-page golden set is the gate, never the tuning set.
TUNING = {
    "word_gap_em": 0.18,   # gap wider than this * em starts a new word
    "cell_gap_em": 1.20,   # gap wider than this * em starts a new cell
    "row_tol_em": 0.45,    # baseline clustering tolerance
    "gutter_min_em": 1.50,    # narrowest zero-coverage x-run that can be a gutter
    "block_gap_lines": 1.60,  # vertical gap > this * median line pitch splits a block
}


def em(spans: Sequence[Span]) -> float:
    """The type size, taken as the median run height."""
    return statistics.median(s.bbox.y1 - s.bbox.y0 for s in spans)


def rows(spans: Sequence[Span], em_: float) -> list[list[Span]]:
    """Group runs into baseline rows, ordered top to bottom."""
    tol = max(2.0, em_ * TUNING["row_tol_em"])
    out: list[list[Span]] = []
    for span in sorted(spans, key=lambda s: ((s.bbox.y0 + s.bbox.y1) / 2, s.bbox.x0)):
        centre = (span.bbox.y0 + span.bbox.y1) / 2
        row = next((r for r in out
                    if abs(centre - sum((s.bbox.y0 + s.bbox.y1) / 2 for s in r) / len(r)) <= tol),
                   None)
        if row is None:
            out.append([span])
        else:
            row.append(span)
    for row in out:
        row.sort(key=lambda s: s.bbox.x0)
    return out


def _join(parts: list[Span]) -> Span:
    """Concatenate abutting runs into one word. Runs carry their own trailing
    spaces, so norm_ws collapses the seams."""
    return Span(
        norm_ws("".join(p.text for p in parts)),
        BBox(min(p.bbox.x0 for p in parts), min(p.bbox.y0 for p in parts),
             max(p.bbox.x1 for p in parts), max(p.bbox.y1 for p in parts)),
        round(statistics.median(p.size for p in parts), 2),
        parts[0].font, parts[0].bold, parts[0].italic,
    )


def cells(row: Sequence[Span], em_: float) -> list[tuple[Span, ...]]:
    """Merge one baseline row's runs into cells, each a tuple of words.

    Runs are atomic — a PDFium text object never spans two columns, so a cell
    boundary is always a run boundary. Two thresholds decide how far to merge:
    a gap under word_gap joins two runs into one word (pages that split words
    mid-glyph), a gap under cell_gap keeps them in the same cell, anything
    wider starts a new cell. Nothing here ever splits a run.
    """
    word_gap, cell_gap = em_ * TUNING["word_gap_em"], em_ * TUNING["cell_gap_em"]
    out: list[tuple[Span, ...]] = []
    words: list[Span] = []
    parts: list[Span] = []
    for span in row:
        if parts:
            gap = span.bbox.x0 - parts[-1].bbox.x1
            if gap > cell_gap:
                words.append(_join(parts))
                out.append(tuple(words))
                words, parts = [], []
            elif gap > word_gap:
                words.append(_join(parts))
                parts = []
        parts.append(span)
    if parts:
        words.append(_join(parts))
    if words:
        out.append(tuple(words))
    return out


def bands(spans: Sequence[Span], width: float, em_: float) -> list[tuple[float, float]]:
    """Column bands, found as maximal x-runs no character crosses.

    Deliberately geometric: the layout model misses 50-65% of spans on dense
    pages, so it can classify columns but must never define them.
    """
    covered = [False] * (int(width) + 1)
    for span in spans:
        for x in range(max(0, int(span.bbox.x0)), min(int(width), int(span.bbox.x1)) + 1):
            covered[x] = True
    if not any(covered):
        return [(0.0, width)]
    first, last = covered.index(True), len(covered) - 1 - covered[::-1].index(True)
    min_gutter = em_ * TUNING["gutter_min_em"]
    out: list[tuple[float, float]] = []
    start, run = first, 0
    for x in range(first, last + 2):
        if x <= last and not covered[x]:
            run += 1
            continue
        if run >= min_gutter and start < x - run:
            out.append((float(start), float(x - run)))
            start = x
        run = 0
    out.append((float(start), float(last + 1)))
    return out or [(float(first), float(last + 1))]


def _band_of(span: Span, found: list[tuple[float, float]]) -> int:
    centre = (span.bbox.x0 + span.bbox.x1) / 2
    for i, (x0, x1) in enumerate(found):
        if x0 <= centre <= x1:
            return i
    return min(range(len(found)),
               key=lambda i: min(abs(centre - found[i][0]), abs(centre - found[i][1])))


def _bbox(spans: Sequence[Span]) -> BBox:
    return BBox(min(s.bbox.x0 for s in spans), min(s.bbox.y0 for s in spans),
                max(s.bbox.x1 for s in spans), max(s.bbox.y1 for s in spans))


def _pitch(band_rows: Sequence[Sequence[Span]]) -> float:
    """Median centre-to-centre distance between consecutive rows — the band's
    own leading, so the block-splitting threshold scales with the page. A
    single gap is not a median of anything; it would just measure itself
    against its own scaled value and could never count as wide, so that case
    falls back to em_ like the empty-band case does."""
    centres = [sum((s.bbox.y0 + s.bbox.y1) / 2 for s in row) / len(row) for row in band_rows]
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    return statistics.median(gaps) if len(gaps) >= 2 else 0.0


def _blocks_in_band(band_rows: Sequence[Sequence[Span]], em_: float) -> list[TextBlock]:
    """Rows into blocks. A row of one cell is prose and joins the paragraph
    above it while the leading stays normal; a row of several cells is a table
    row whose cells each stay their own block, so cell atomicity survives."""
    limit = (_pitch(band_rows) or em_) * TUNING["block_gap_lines"]
    out: list[TextBlock] = []
    para: list[TextLine] = []

    def flush() -> None:
        if para:
            out.append(TextBlock(_bbox([s for line in para for s in line.spans]), tuple(para)))
            para.clear()

    for row in band_rows:
        row_cells = cells(row, em_)
        lines = [TextLine(_bbox(cell), cell) for cell in row_cells]
        if len(lines) == 1:
            if para and lines[0].bbox.y0 - para[-1].bbox.y1 > limit:
                flush()
            para.append(lines[0])
        else:
            flush()
            out.extend(TextBlock(line.bbox, (line,)) for line in lines)
    flush()
    return out


def build(spans: Sequence[Span], width: float, height: float) -> tuple[TextBlock, ...]:
    """Atomic runs with geometry into blocks: bands, then rows, then cells,
    then paragraph grouping.

    Reading order is band order, then top to bottom. Nothing merges across a
    band, and no line merges across a cell boundary.
    """
    if not spans:
        return ()
    em_ = em(spans)
    found = bands(spans, width, em_)
    out: list[TextBlock] = []
    for index in range(len(found)):
        in_band = [s for s in spans if _band_of(s, found) == index]
        if not in_band:
            continue
        out.extend(_blocks_in_band(rows(in_band, em_), em_))
    return tuple(out)

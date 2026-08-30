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
    "row_fill_table": 0.70,  # a run of consecutive multi-cell rows is a table
                             # when its median fill ratio (text width / row
                             # width) is below this; measured, not tuned here
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


def _blocks_in_band(band_rows: Sequence[Sequence[Span]], em_: float,
                     breaks: Sequence[tuple[float, float]] = ()) -> list[TextBlock]:
    """Rows into blocks. A row of one cell is prose and joins the paragraph
    above it while the leading stays normal and no table row falls between;
    a row of several cells is a table row whose cells each stay their own
    block, so cell atomicity survives.

    `breaks` are the y-ranges of table rows build() already pulled out of
    this band's spans. A table interrupts every column's flow at its own
    height even though its own cells never reach this band, so without this
    check the paragraph grouper — seeing only the two now-adjacent prose
    rows — would silently stitch them back together across the table.
    """
    limit = (_pitch(band_rows) or em_) * TUNING["block_gap_lines"]
    out: list[TextBlock] = []
    para: list[TextLine] = []

    def crosses_a_break(y0: float, y1: float) -> bool:
        return any(y0 <= (b0 + b1) / 2 <= y1 for b0, b1 in breaks)

    def flush() -> None:
        if para:
            out.append(TextBlock(_bbox([s for line in para for s in line.spans]), tuple(para)))
            para.clear()

    for row in band_rows:
        row_cells = cells(row, em_)
        lines = [TextLine(_bbox(cell), cell) for cell in row_cells]
        if len(lines) == 1:
            if para and (lines[0].bbox.y0 - para[-1].bbox.y1 > limit
                         or crosses_a_break(para[-1].bbox.y1, lines[0].bbox.y0)):
                flush()
            para.append(lines[0])
        else:
            flush()
            out.extend(TextBlock(line.bbox, (line,)) for line in lines)
    flush()
    return out


def _fill(row_cells: Sequence[tuple[Span, ...]]) -> float:
    """Fraction of a row's horizontal extent actually covered by text.

    Gap width alone cannot separate a table's own column gap from a page
    gutter — both are wide relative to the type size, and their measured
    distributions overlap. Fill does: a table's value cells stay narrow next
    to a wide gap (median 0.24-0.48 on real pages), while a page column's
    line word-wraps to fill its width (median 0.87-0.95) even when it shares
    a baseline with the column beside it.
    """
    covered = sum(_bbox(cell).x1 - _bbox(cell).x0 for cell in row_cells)
    extent = _bbox(row_cells[-1]).x1 - _bbox(row_cells[0]).x0
    return covered / extent if extent > 0 else 1.0


def _table_run(indices: Sequence[int], row_cells: Sequence[list[tuple[Span, ...]]]) -> bool:
    """A maximal run of consecutive multi-cell rows is a table when its
    median fill ratio is low. Decided per run, not per row: a paragraph's
    short final line has a low fill on its own and would be misread as a
    table row if judged alone."""
    return statistics.median(_fill(row_cells[i]) for i in indices) < TUNING["row_fill_table"]


def build(spans: Sequence[Span], width: float, height: float) -> tuple[TextBlock, ...]:
    """Atomic runs with geometry into blocks.

    Rows are clustered across the whole page, not per band first — bands()
    cannot tell a table's own column gap from a real page gutter, so gating
    on bands would tear tables into per-column blocks again. A maximal run of
    consecutive rows that each segment into two or more cells is a table when
    its fill ratio is low; each of its rows becomes one atomic block, a line
    per cell, so a wide row survives downstream reordering intact. Every
    other row is band-assigned and grouped into paragraphs as before — a
    table row still interrupts that grouping at its own height (see
    _blocks_in_band's `breaks`), even though it never reaches a band's span
    list.
    """
    if not spans:
        return ()
    em_ = em(spans)
    all_rows = rows(spans, em_)
    row_cells = [cells(row, em_) for row in all_rows]

    runs: list[list[int]] = []
    current: list[int] = []
    for i, rc in enumerate(row_cells):
        if len(rc) >= 2:
            current.append(i)
        else:
            if current:
                runs.append(current)
            current = []
    if current:
        runs.append(current)
    table_rows = {i for run in runs if _table_run(run, row_cells) for i in run}

    out: list[TextBlock] = []
    column_spans: list[Span] = []
    breaks: list[tuple[float, float]] = []
    for i, row in enumerate(all_rows):
        if i in table_rows:
            lines = tuple(TextLine(_bbox(cell), cell) for cell in row_cells[i])
            block = TextBlock(_bbox(row), lines)
            out.append(block)
            breaks.append((block.bbox.y0, block.bbox.y1))
        else:
            column_spans.extend(row)

    if column_spans:
        found = bands(column_spans, width, em_)
        for index in range(len(found)):
            band_rows = rows([s for s in column_spans if _band_of(s, found) == index], em_)
            out.extend(_blocks_in_band(band_rows, em_, breaks))

    out.sort(key=lambda b: (b.bbox.y0, b.bbox.x0))
    return tuple(out)

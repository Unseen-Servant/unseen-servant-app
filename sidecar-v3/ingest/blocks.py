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
from ingest.raw import Span, norm_ws

# Tunable constants, expressed as multiples of the row's em (its type size) so
# they scale with the page instead of assuming one. Per the plan's
# anti-overfitting rule these may be tuned ONLY against the ten section 4.3
# fixture pages; the 40-page golden set is the gate, never the tuning set.
TUNING = {
    "word_gap_em": 0.18,   # gap wider than this * em starts a new word
    "cell_gap_em": 1.20,   # gap wider than this * em starts a new cell
    "row_tol_em": 0.45,    # baseline clustering tolerance
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

"""PDFium Stage-A candidate: character geometry -> safe native line blocks.

PDFium exposes text as a character stream rather than PyMuPDF-style blocks.
This adapter deliberately keeps its own units to one reconstructed line: a
later layout pass may order and classify lines, but it never has permission to
merge same-y content across columns.
"""
from __future__ import annotations

import statistics
from pathlib import Path

import numpy as np
import pypdfium2

from domain.models import BBox
from ingest.extract import PageExtract, RawExtraction, Span, TextBlock, TextLine, _norm_ws


def _line_spans(text_page, height: float) -> list[list[Span]]:
    chars: list[Span] = []
    pending_space = False
    for i in range(text_page.count_chars()):
        char = text_page.get_text_range(i, 1)
        if not char:
            continue
        if char.isspace():
            pending_space = True
            continue
        x0, y0, x1, y1 = text_page.get_charbox(i)
        if x1 <= x0 or y1 <= y0:
            continue
        # PDFium measures y up from the bottom of the page; BBox and every
        # consumer of it use PyMuPDF's y-down top-left origin. Convert here so
        # the row sort below reads the page top-to-bottom.
        chars.append(Span((" " if pending_space else "") + char,
                          BBox(x0, height - y1, x1, height - y0), round(y1 - y0, 2), ""))
        pending_space = False
    if not chars:
        return []

    height = statistics.median(char.bbox.y1 - char.bbox.y0 for char in chars)
    rows: list[list[Span]] = []
    for char in sorted(chars, key=lambda item: ((item.bbox.y0 + item.bbox.y1) / 2, item.bbox.x0)):
        center = (char.bbox.y0 + char.bbox.y1) / 2
        row = next((candidate for candidate in rows
                    if abs(center - sum((item.bbox.y0 + item.bbox.y1) / 2 for item in candidate) / len(candidate))
                    <= max(2.0, height * 0.45)), None)
        if row is None:
            rows.append([char])
        else:
            row.append(char)

    lines: list[list[Span]] = []
    for row in rows:
        row.sort(key=lambda item: item.bbox.x0)
        widths = [item.bbox.x1 - item.bbox.x0 for item in row]
        split_gap = max(18.0, statistics.median(widths) * 6)
        line: list[Span] = []
        for char in row:
            if line and char.bbox.x0 - line[-1].bbox.x1 > split_gap:
                lines.append(line)
                line = []
            line.append(char)
        if line:
            lines.append(line)
    return lines


def _words(chars: list[Span]) -> tuple[Span, ...]:
    words: list[Span] = []
    current: list[Span] = []
    for char in chars:
        if current and char.bbox.x0 - current[-1].bbox.x1 > 3.0:
            words.append(_word(current))
            current = []
        current.append(char)
    if current:
        words.append(_word(current))
    return tuple(words)


def _word(chars: list[Span]) -> Span:
    return Span(
        _norm_ws("".join(char.text for char in chars)),
        BBox(min(char.bbox.x0 for char in chars), min(char.bbox.y0 for char in chars),
             max(char.bbox.x1 for char in chars), max(char.bbox.y1 for char in chars)),
        round(statistics.median(char.size for char in chars), 2), "",
    )


def _page_blocks(page, height: float) -> tuple[TextBlock, ...]:
    lines = _line_spans(page.get_textpage(), height)
    out = []
    for chars in lines:
        spans = _words(chars)
        if not spans:
            continue
        bbox = BBox(min(span.bbox.x0 for span in spans), min(span.bbox.y0 for span in spans),
                    max(span.bbox.x1 for span in spans), max(span.bbox.y1 for span in spans))
        out.append(TextBlock(bbox, (TextLine(bbox, spans),)))
    return tuple(out)


def extract(pdf_path, doc_id: str | None = None) -> RawExtraction:
    path = str(pdf_path)
    pdf = pypdfium2.PdfDocument(path)
    pages = []
    for i, page in enumerate(pdf):
        width, height = page.get_size()
        blocks = _page_blocks(page, height)
        spans = tuple(span for block in blocks for span in block.spans)
        pages.append(PageExtract(i, width, height, spans, not spans, "", blocks))
    did = doc_id or Path(path).stem
    return RawExtraction(did, path, did, len(pdf), (), tuple("" for _ in pages), tuple(pages), any(p.needs_ocr for p in pages))


def rasterize(pdf_path, page_index: int, dpi: int = 150) -> np.ndarray:
    pdf = pypdfium2.PdfDocument(str(pdf_path))
    bitmap = pdf[page_index].render(scale=dpi / 72)
    image = bitmap.to_numpy()
    return image[:, :, :3].copy()

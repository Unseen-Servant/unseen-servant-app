"""pdfplumber Stage-A candidate using word geometry rather than character inference."""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from domain.models import BBox
from ingest.raw import PageExtract, RawExtraction, Span, TextBlock, TextLine


def _blocks(page) -> tuple[TextBlock, ...]:
    words = page.extract_words(extra_attrs=["fontname", "size"])
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        row = next((candidate for candidate in rows
                    if abs(word["top"] - sum(item["top"] for item in candidate) / len(candidate)) <= 3), None)
        if row is None:
            rows.append([word])
        else:
            row.append(word)
    out = []
    for row in rows:
        row.sort(key=lambda item: item["x0"])
        lines: list[list[dict]] = [[]]
        for word in row:
            if lines[-1] and word["x0"] - lines[-1][-1]["x1"] > page.width * 0.18:
                lines.append([])
            lines[-1].append(word)
        for words_in_line in lines:
            spans = tuple(Span(
                item["text"], BBox(item["x0"], item["top"], item["x1"], item["bottom"]),
                round(float(item.get("size", item["bottom"] - item["top"])), 2), item.get("fontname", ""),
                bold="bold" in item.get("fontname", "").lower(),
                italic="italic" in item.get("fontname", "").lower() or "oblique" in item.get("fontname", "").lower(),
            ) for item in words_in_line)
            bbox = BBox(min(item.bbox.x0 for item in spans), min(item.bbox.y0 for item in spans),
                        max(item.bbox.x1 for item in spans), max(item.bbox.y1 for item in spans))
            out.append(TextBlock(bbox, (TextLine(bbox, spans),)))
    return tuple(out)


def extract(pdf_path, doc_id: str | None = None) -> RawExtraction:
    path = str(pdf_path)
    with pdfplumber.open(path) as pdf:
        pages = []
        for i, page in enumerate(pdf.pages):
            blocks = _blocks(page)
            spans = tuple(span for block in blocks for span in block.spans)
            pages.append(PageExtract(i, page.width, page.height, spans, not spans and bool(page.images), "", blocks))
    did = doc_id or Path(path).stem
    return RawExtraction(did, path, did, len(pages), (), tuple("" for _ in pages), tuple(pages), any(p.needs_ocr for p in pages))

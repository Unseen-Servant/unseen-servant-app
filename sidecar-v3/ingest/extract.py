"""A. Raw extraction (PyMuPDF) — plan §3.2 A.

`get_text("dict")` spans with font/bbox, page geometry, TOC, and printed page
labels (`page.get_label()`); text-layerless pages flagged `needs_ocr`. Also
rasterizes a page at ~150 DPI for the Stage B layout model (PP-DocLayout-M ONNX).

This is the raw, pre-typed input to Stage B (layout) — NOT the persisted IR.
Spans are transient ingestion state (fitz/numpy-adjacent), so they live here, not
in domain/models.py (constitution #6: the domain IR is the clean typed product).
Reuses the shared geometry type `domain.models.BBox`. No import from sidecar/.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf

from domain.models import BBox
from ingest.raw import (
    PageExtract, RawExtraction, Span, TextBlock, TextLine, norm_ws as _norm_ws,
)

# PyMuPDF get_text("dict") span flag bits.
_ITALIC = 1 << 1
_BOLD = 1 << 4


def _page_text_blocks(page) -> tuple[TextBlock, ...]:
    out: list[TextBlock] = []
    for block in page.get_text("dict")["blocks"]:
        lines: list[TextLine] = []
        for line in block.get("lines", []):
            spans: list[Span] = []
            for s in line.get("spans", []):
                text = _norm_ws(s["text"])
                if not text:
                    continue
                font = s.get("font", "")
                flags = s.get("flags", 0)
                low = font.lower()
                spans.append(Span(
                    text=text,
                    bbox=BBox(*s["bbox"]),
                    size=round(float(s["size"]), 2),
                    font=font,
                    bold=bool(flags & _BOLD) or "bold" in low,
                    italic=bool(flags & _ITALIC) or "italic" in low or "oblique" in low,
                ))
            if spans:
                lines.append(TextLine(BBox(*line["bbox"]), tuple(spans)))
        if lines:
            out.append(TextBlock(BBox(*block["bbox"]), tuple(lines)))
    return tuple(out)


def extract(pdf_path, doc_id: str | None = None) -> RawExtraction:
    """Open a PDF and produce its raw Stage A extraction."""
    path = str(pdf_path)
    with pymupdf.open(path) as doc:
        did = doc_id or Path(path).stem
        pages: list[PageExtract] = []
        for i in range(doc.page_count):
            page = doc.load_page(i)
            blocks = _page_text_blocks(page)
            spans = tuple(span for block in blocks for span in block.spans)
            pages.append(PageExtract(
                page=i,
                width=float(page.rect.width),
                height=float(page.rect.height),
                spans=spans,
                needs_ocr=(not spans and bool(page.get_images())),
                label=page.get_label() or "",
                blocks=blocks,
            ))
        toc = tuple((lvl, title, pno) for lvl, title, pno in doc.get_toc())
        title = (doc.metadata or {}).get("title") or did
        return RawExtraction(
            doc_id=did,
            path=path,
            title=title,
            page_count=doc.page_count,
            toc=toc,
            page_labels=tuple(p.label for p in pages),
            pages=tuple(pages),
            needs_ocr=any(p.needs_ocr for p in pages),
        )


def rasterize(pdf_path, page_index: int, dpi: int = 150) -> np.ndarray:
    """Render a page to an RGB uint8 array (H, W, 3) for the layout model."""
    with pymupdf.open(str(pdf_path)) as doc:
        pix = doc.load_page(page_index).get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72))
        return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()

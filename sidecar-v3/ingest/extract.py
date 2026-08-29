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

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymupdf

from domain.models import BBox

# PyMuPDF get_text("dict") span flag bits.
_ITALIC = 1 << 1
_BOLD = 1 << 4

# Some PDFs embed \t \r \xa0 runs inside their text spans; collapse each run to a
# single space at the source so no downstream consumer (block, chunk payload,
# unit) has to. \s is Unicode-aware, so it also folds the non-breaking space.
_WS_RUN = re.compile(r"\s+")


def _norm_ws(text: str) -> str:
    return _WS_RUN.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Span:
    """One text run from `get_text("dict")` — text + bbox (PDF points) + font.
    Stage B assigns spans to detected layout regions."""

    text: str
    bbox: BBox
    size: float
    font: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True, slots=True)
class TextLine:
    """One native PDF line. Its span order is the extractor's source order."""

    bbox: BBox
    spans: tuple[Span, ...]

    @property
    def text(self) -> str:
        return " ".join(span.text for span in self.spans)


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One native PDF text block. Layout may classify it but never reshape it."""

    bbox: BBox
    lines: tuple[TextLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def spans(self) -> tuple[Span, ...]:
        return tuple(span for line in self.lines for span in line.spans)


@dataclass(frozen=True, slots=True)
class PageExtract:
    """Raw extraction for one page. `raster` is produced on demand by
    `rasterize()` (transient, never persisted), not stored here."""

    page: int  # 0-based physical index
    width: float  # PDF points
    height: float
    spans: tuple[Span, ...]
    needs_ocr: bool  # no text layer but has image content (opt-in slow OCR pass)
    label: str  # printed page label (page.get_label()), "" if none
    blocks: tuple[TextBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class RawExtraction:
    """Document-level Stage A output: per-page spans + doc metadata."""

    doc_id: str
    path: str
    title: str
    page_count: int
    toc: tuple[tuple[int, str, int], ...]  # (level, title, 1-based page)
    page_labels: tuple[str, ...]
    pages: tuple[PageExtract, ...]
    needs_ocr: bool  # any page lacked a text layer


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

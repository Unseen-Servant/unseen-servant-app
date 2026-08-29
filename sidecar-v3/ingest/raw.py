"""Backend-neutral raw extraction types — the typed Stage A product.

These are transient ingestion state, not the persisted IR (constitution #6:
domain/models.py carries the clean typed product). They live here rather than
in a backend module so that no aggregation and no candidate backend imports a
PDF library it does not use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from domain.models import BBox

# Some PDFs embed \t \r \xa0 runs inside their text spans; collapse each run to
# a single space at the source so no downstream consumer (block, chunk payload,
# unit) has to. \s is Unicode-aware, so it also folds the non-breaking space.
_WS_RUN = re.compile(r"\s+")


def norm_ws(text: str) -> str:
    return _WS_RUN.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Span:
    """One text run — text + bbox (PDF points, y-down from top-left) + font."""

    text: str
    bbox: BBox
    size: float
    font: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True, slots=True)
class TextLine:
    """One line. Its span order is the extractor's source order."""

    bbox: BBox
    spans: tuple[Span, ...]

    @property
    def text(self) -> str:
        return " ".join(span.text for span in self.spans)


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One text block. Layout may classify it but never reshape it."""

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
    """Raw extraction for one page. `raster` is produced on demand by a
    backend's `rasterize()` (transient, never persisted), not stored here."""

    page: int  # 0-based physical index
    width: float  # PDF points
    height: float
    spans: tuple[Span, ...]
    needs_ocr: bool  # no text layer but has image content (opt-in slow OCR pass)
    label: str  # printed page label, "" if none
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

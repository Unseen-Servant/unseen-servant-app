"""PyMuPDF layout-preserving extraction using block/line geometry.

Default get_text("text") linearizes multi-column pages poorly (columns interleaved,
table cells flattened to one cell per line). This variant uses get_text("dict")
to recover block order sorted by (x0, y0) buckets, which keeps columns separate
and preserves horizontal grouping of table cells.
"""
from __future__ import annotations

import time
from pathlib import Path

import fitz  # pymupdf

from extract_pypdf import ExtractionResult, PageExtraction


def _extract_page_layout(page: fitz.Page) -> str:
    """Reconstruct text respecting column layout.

    Strategy: get blocks, group into columns by x0, within each column sort by
    y0, within each line join spans with horizontal gaps preserved as spaces.
    This is deliberately simple — not a full layout engine, just enough to
    keep tables and columns legible.
    """
    data = page.get_text("dict")
    blocks = [b for b in data.get("blocks", []) if b.get("type") == 0]  # text blocks only
    if not blocks:
        return ""

    page_width = page.rect.width
    # Two-column heuristic: anything starting left of midline goes to col 0, else col 1.
    # Single-column PDFs will just all land in one bucket.
    columns: dict[int, list[dict]] = {0: [], 1: []}
    for b in blocks:
        x0 = b["bbox"][0]
        col = 0 if x0 < page_width / 2 else 1
        columns[col].append(b)

    out_parts: list[str] = []
    for col_idx in (0, 1):
        col_blocks = sorted(columns[col_idx], key=lambda b: (b["bbox"][1], b["bbox"][0]))
        for block in col_blocks:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                # Preserve horizontal gaps: if span x0 is much greater than previous
                # span x1, insert extra spacing (helps table-like layouts).
                parts: list[str] = []
                prev_x1: float | None = None
                for s in sorted(spans, key=lambda s: s["bbox"][0]):
                    txt = s.get("text", "")
                    if prev_x1 is not None:
                        gap = s["bbox"][0] - prev_x1
                        # Heuristic: gap > ~1 em suggests tab/column separator.
                        if gap > 20:
                            parts.append("\t")
                        elif gap > 5:
                            parts.append(" ")
                    parts.append(txt)
                    prev_x1 = s["bbox"][2]
                out_parts.append("".join(parts))
            out_parts.append("")  # blank line between blocks
    return "\n".join(out_parts)


def extract(pdf_path: Path) -> ExtractionResult:
    pages: list[PageExtraction] = []
    t0 = time.perf_counter()
    try:
        doc = fitz.open(pdf_path)
        try:
            for i, page in enumerate(doc):
                p0 = time.perf_counter()
                text = _extract_page_layout(page)
                pages.append(PageExtraction(page_index=i, text=text, seconds=time.perf_counter() - p0))
        finally:
            doc.close()
    except Exception as e:
        return ExtractionResult(
            extractor="pymupdf-layout", pdf_path=pdf_path, pages=pages,
            total_seconds=time.perf_counter() - t0, error=str(e),
        )
    return ExtractionResult(
        extractor="pymupdf-layout", pdf_path=pdf_path, pages=pages,
        total_seconds=time.perf_counter() - t0, error=None,
    )

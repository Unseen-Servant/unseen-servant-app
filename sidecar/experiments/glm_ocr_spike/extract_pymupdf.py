"""PyMuPDF (fitz) text extraction. Cheaper baseline than GLM-OCR; better layout than pypdf."""
from __future__ import annotations

import time
from pathlib import Path

import fitz  # pymupdf

from extract_pypdf import ExtractionResult, PageExtraction


def extract(pdf_path: Path) -> ExtractionResult:
    pages: list[PageExtraction] = []
    t0 = time.perf_counter()
    try:
        doc = fitz.open(pdf_path)
        try:
            for i, page in enumerate(doc):
                p0 = time.perf_counter()
                text = page.get_text("text") or ""
                pages.append(PageExtraction(page_index=i, text=text, seconds=time.perf_counter() - p0))
        finally:
            doc.close()
    except Exception as e:
        return ExtractionResult(
            extractor="pymupdf", pdf_path=pdf_path, pages=pages,
            total_seconds=time.perf_counter() - t0, error=str(e),
        )
    return ExtractionResult(
        extractor="pymupdf", pdf_path=pdf_path, pages=pages,
        total_seconds=time.perf_counter() - t0, error=None,
    )

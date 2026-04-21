"""pypdf extraction, matching the production path in sidecar/server.py:prepare_pdf."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class PageExtraction:
    page_index: int
    text: str
    seconds: float


@dataclass
class ExtractionResult:
    extractor: str
    pdf_path: Path
    pages: list[PageExtraction]
    total_seconds: float
    error: str | None = None

    @property
    def full_text(self) -> str:
        return "".join(p.text for p in self.pages)


def extract(pdf_path: Path) -> ExtractionResult:
    pages: list[PageExtraction] = []
    t0 = time.perf_counter()
    try:
        reader = PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            p0 = time.perf_counter()
            text = page.extract_text() or ""
            pages.append(PageExtraction(page_index=i, text=text, seconds=time.perf_counter() - p0))
    except Exception as e:
        return ExtractionResult(
            extractor="pypdf", pdf_path=pdf_path, pages=pages,
            total_seconds=time.perf_counter() - t0, error=str(e),
        )
    return ExtractionResult(
        extractor="pypdf", pdf_path=pdf_path, pages=pages,
        total_seconds=time.perf_counter() - t0, error=None,
    )

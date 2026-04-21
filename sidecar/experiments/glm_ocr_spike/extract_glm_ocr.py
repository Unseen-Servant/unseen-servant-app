"""GLM-OCR extraction: rasterize each page with PyMuPDF, send to ollama.chat(model='glm-ocr')."""
from __future__ import annotations

import time
from pathlib import Path

import fitz  # pymupdf
import ollama

from extract_pypdf import ExtractionResult, PageExtraction

DEFAULT_MODEL = "glm-ocr"
DEFAULT_DPI = 150
DEFAULT_PROMPT = (
    "Convert this PDF page to clean Markdown. Preserve headings, tables (as Markdown tables), "
    "lists, and stat-block structure. Do not invent content that is not visible on the page. "
    "If the page is blank or unreadable, return an empty response."
)


def _render_page_png(page: fitz.Page, dpi: int) -> bytes:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


def extract(
    pdf_path: Path,
    *,
    model: str = DEFAULT_MODEL,
    dpi: int = DEFAULT_DPI,
    prompt: str = DEFAULT_PROMPT,
    page_limit: int | None = None,
    client: ollama.Client | None = None,
) -> ExtractionResult:
    """Extract Markdown from a PDF one page at a time via GLM-OCR.

    page_limit caps pages processed (for fast spot-checks); None = all pages.
    """
    pages: list[PageExtraction] = []
    t0 = time.perf_counter()
    oc = client or ollama.Client()
    try:
        doc = fitz.open(pdf_path)
        try:
            for i, page in enumerate(doc):
                if page_limit is not None and i >= page_limit:
                    break
                p0 = time.perf_counter()
                png = _render_page_png(page, dpi)
                try:
                    resp = oc.chat(
                        model=model,
                        messages=[{"role": "user", "content": prompt, "images": [png]}],
                    )
                    text = (resp.get("message", {}) or {}).get("content", "") or ""
                except Exception as e:
                    text = ""
                    pages.append(PageExtraction(
                        page_index=i, text=f"<!-- glm-ocr error: {e} -->\n",
                        seconds=time.perf_counter() - p0,
                    ))
                    continue
                pages.append(PageExtraction(page_index=i, text=text, seconds=time.perf_counter() - p0))
        finally:
            doc.close()
    except Exception as e:
        return ExtractionResult(
            extractor=f"glm-ocr@{dpi}", pdf_path=pdf_path, pages=pages,
            total_seconds=time.perf_counter() - t0, error=str(e),
        )
    return ExtractionResult(
        extractor=f"glm-ocr@{dpi}", pdf_path=pdf_path, pages=pages,
        total_seconds=time.perf_counter() - t0, error=None,
    )

"""PDFium Stage-A adapter: one Span per text object, y-up flipped to y-down.

PDFium exposes text as page objects, not PyMuPDF-style blocks. This adapter's
only job is to turn each text object into a Span in the pipeline's convention
and hand the page's spans to ingest.blocks.build(), which owns all
aggregation — words, cells, and blocks are never grouped here.
"""
from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np
import pypdfium2
import pypdfium2.raw as pdfium_raw

from domain.models import BBox
from ingest.blocks import build
from ingest.raw import PageExtract, RawExtraction, Span, norm_ws


def _span(text: str, bounds: tuple[float, float, float, float], height: float,
          font: str, weight: int, italic_angle: int) -> Span | None:
    text = norm_ws(text)
    if not text:
        return None
    left, bottom, right, top = bounds
    if right <= left or top <= bottom:
        return None
    # PDFium measures y up from the bottom of the page; BBox and every
    # consumer of it (blocks.build, the layout raster) use PyMuPDF's y-down
    # top-left origin. Convert here, at the source.
    bbox = BBox(left, height - top, right, height - bottom)
    return Span(text, bbox, round(bbox.y1 - bbox.y0, 2), font, weight >= 700, italic_angle != 0)


def _object_text(obj, text_page) -> str:
    length = pdfium_raw.FPDFTextObj_GetText(obj.raw, text_page.raw, None, 0)
    if length <= 0:
        return ""
    buf = ctypes.create_string_buffer(length)
    pdfium_raw.FPDFTextObj_GetText(obj.raw, text_page.raw, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), length)
    return buf.raw[:length].decode("utf-16-le", errors="ignore").rstrip("\x00")


def _object_font(obj) -> tuple[str, int, int]:
    font = pdfium_raw.FPDFTextObj_GetFont(obj.raw)
    length = pdfium_raw.FPDFFont_GetBaseFontName(font, None, 0)
    name = ""
    if length > 0:
        buf = ctypes.create_string_buffer(length)
        pdfium_raw.FPDFFont_GetBaseFontName(font, buf, length)
        name = buf.value.decode("utf-8", errors="replace")
    weight = pdfium_raw.FPDFFont_GetWeight(font)
    angle = ctypes.c_int(0)
    pdfium_raw.FPDFFont_GetItalicAngle(font, ctypes.byref(angle))
    return name, weight, angle.value


def _objects(page, text_page) -> tuple[Span, ...]:
    height = page.get_size()[1]
    out = []
    for obj in page.get_objects():
        if obj.type != pdfium_raw.FPDF_PAGEOBJ_TEXT:
            continue
        text = _object_text(obj, text_page)
        if not text:
            continue
        font, weight, angle = _object_font(obj)
        span = _span(text, obj.get_bounds(), height, font, weight, angle)
        if span is not None:
            out.append(span)
    return tuple(out)


def extract(pdf_path, doc_id: str | None = None) -> RawExtraction:
    path = str(pdf_path)
    pdf = pypdfium2.PdfDocument(path)
    pages = []
    for i, page in enumerate(pdf):
        width, height = page.get_size()
        text_page = page.get_textpage()
        blocks = build(_objects(page, text_page), width, height)
        spans = tuple(span for block in blocks for span in block.spans)
        pages.append(PageExtract(i, width, height, spans, not spans, "", blocks))
    did = doc_id or Path(path).stem
    return RawExtraction(did, path, did, len(pdf), (), tuple("" for _ in pages), tuple(pages), any(p.needs_ocr for p in pages))


def rasterize(pdf_path, page_index: int, dpi: int = 150) -> np.ndarray:
    pdf = pypdfium2.PdfDocument(str(pdf_path))
    bitmap = pdf[page_index].render(scale=dpi / 72)
    image = bitmap.to_numpy()
    return image[:, :, :3].copy()

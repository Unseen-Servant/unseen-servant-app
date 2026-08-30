"""Document metadata from PDFium: title, outline, printed page labels.

The v3 storage schema persists toc and page_labels, so an adapter that returns
them empty fails the metadata gate (spec section 6).
"""
from __future__ import annotations

import ctypes

import pypdfium2.raw as pdfium_raw


def _utf16(fn, *args) -> str:
    length = fn(*args, None, 0)
    if length <= 0:
        return ""
    buf = ctypes.create_string_buffer(length)
    fn(*args, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), length)
    return buf.raw.decode("utf-16-le", errors="ignore").rstrip("\x00")


def title(pdf, fallback: str) -> str:
    return _utf16(pdfium_raw.FPDF_GetMetaText, pdf.raw, b"Title") or fallback


def toc(pdf) -> tuple[tuple[int, str, int], ...]:
    """(level, title, 1-based page), matching PyMuPDF's get_toc().

    pypdfium2 reports a 0-based bookmark level and a 0-based destination page
    index; PyMuPDF reports both 1-based.
    """
    out = []
    for bookmark in pdf.get_toc():
        dest = bookmark.get_dest()
        index = dest.get_index() if dest is not None else None
        page = (index + 1) if index is not None else -1
        out.append((bookmark.level + 1, bookmark.get_title() or "", page))
    return tuple(out)


def page_labels(pdf, page_count: int) -> tuple[str, ...]:
    return tuple(_utf16(pdfium_raw.FPDF_GetPageLabel, pdf.raw, i) for i in range(page_count))

"""Stage A — raw extraction (plan §3.2 A). Fixtures are tiny fitz-authored
PDFs (self-contained, no corpus / no network), so this runs in CI."""
import fitz
import numpy as np
import pytest

from domain.models import BBox
from ingest.extract import extract, rasterize, Span, PageExtract, RawExtraction, _norm_ws


@pytest.fixture
def text_pdf(tmp_path):
    """Two pages: a bold heading + prose on p1, prose on p2, with a TOC."""
    doc = fitz.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((72, 90), "The Goblin", fontsize=18, fontname="hebo")   # bold
    p1.insert_text((72, 140), "A goblin has armor class 15.", fontsize=11, fontname="helv")
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((72, 90), "Second page prose.", fontsize=11, fontname="helv")
    doc.set_toc([[1, "The Goblin", 1]])
    path = tmp_path / "text.pdf"
    doc.save(path)
    return str(path)


def test_norm_ws_collapses_tab_cr_nbsp_runs():
    # Some PDFs (e.g. the 5e SRD) embed \t\r\xa0 runs between every token; left
    # raw they turn the chunk payload into "15\t\r \xa0(leather\t\r \xa0armor)".
    assert _norm_ws("15\t\r \xa0(leather\t\r \xa0armor,\t\r \xa0shield)\t\r \xa0") \
        == "15 (leather armor, shield)"
    assert _norm_ws("Armor\xa0Class 15") == "Armor Class 15"
    assert _norm_ws("  padded  ") == "padded"


def test_spans_strip_embedded_whitespace_runs(tmp_path):
    # A span whose text carries nbsp litter must be normalized at the source, so
    # every downstream consumer (block, chunk payload, unit) sees clean text.
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 90), "Armor\xa0Class\xa015\xa0(leather\xa0armor)", fontsize=11, fontname="helv")
    path = tmp_path / "litter.pdf"
    doc.save(path)
    ex = extract(str(path), doc_id="fix")
    joined = " ".join(s.text for s in ex.pages[0].spans)
    assert "\xa0" not in joined
    assert "Armor Class 15 (leather armor)" in joined


@pytest.fixture
def image_only_pdf(tmp_path):
    """One page with an image and no text layer — the needs_ocr case."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 64, 64))
    pix.clear_with(200)
    page.insert_image(fitz.Rect(20, 20, 280, 280), pixmap=pix)
    path = tmp_path / "scan.pdf"
    doc.save(path)
    return str(path)


def test_spans_carry_text_bbox_and_bold(text_pdf):
    ex = extract(text_pdf, doc_id="fix")
    spans = ex.pages[0].spans
    heading = next(s for s in spans if "Goblin" in s.text)
    prose = next(s for s in spans if "armor class" in s.text)
    assert isinstance(heading, Span)
    assert heading.bold and not prose.bold
    assert heading.size > prose.size
    assert isinstance(heading.bbox, BBox) and heading.bbox.x1 > heading.bbox.x0 > 0


def test_reports_page_count_and_geometry(text_pdf):
    ex = extract(text_pdf, doc_id="fix")
    assert isinstance(ex, RawExtraction)
    assert ex.page_count == 2 and len(ex.pages) == 2
    assert ex.pages[0].page == 0 and ex.pages[1].page == 1
    assert (ex.pages[0].width, ex.pages[0].height) == (612.0, 792.0)


def test_captures_toc(text_pdf):
    ex = extract(text_pdf, doc_id="fix")
    assert ex.toc == ((1, "The Goblin", 1),)


def test_page_labels_len_matches_pages(text_pdf):
    ex = extract(text_pdf, doc_id="fix")
    assert len(ex.page_labels) == ex.page_count
    assert all(isinstance(x, str) for x in ex.page_labels)


def test_text_page_is_not_needs_ocr(text_pdf):
    ex = extract(text_pdf, doc_id="fix")
    assert ex.needs_ocr is False
    assert all(not p.needs_ocr for p in ex.pages)


def test_image_only_page_flags_needs_ocr(image_only_pdf):
    ex = extract(image_only_pdf, doc_id="scan")
    assert ex.pages[0].needs_ocr is True
    assert ex.needs_ocr is True
    assert ex.pages[0].spans == ()


def test_rasterize_returns_rgb_uint8_at_dpi(text_pdf):
    img = rasterize(text_pdf, 0, dpi=150)
    assert img.dtype == np.uint8 and img.ndim == 3 and img.shape[2] == 3
    assert abs(img.shape[0] - round(792 * 150 / 72)) <= 2   # height in px
    assert abs(img.shape[1] - round(612 * 150 / 72)) <= 2   # width in px


def test_doc_id_defaults_to_filename_stem(text_pdf):
    ex = extract(text_pdf)
    assert ex.doc_id == "text"

"""The PDFium adapter is thin: one Span per text object, all aggregation in
ingest.blocks. These tests pin the seam, not the aggregation."""
from domain.models import BBox
from ingest.pdfium_extract import _span

PAGE_HEIGHT = 100.0
BOUNDS = (10.0, 80.0, 40.0, 90.0)  # PDFium: (left, bottom, right, top), y-up


def test_span_reports_top_left_origin_boxes():
    """PDFium measures y up from the bottom; BBox and every consumer of it use
    PyMuPDF's y-down top-left origin, the layout raster included."""
    got = _span("Gambeson", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0)
    assert got.bbox == BBox(10.0, 10.0, 40.0, 20.0)


def test_span_size_comes_from_the_bounds_not_the_font_size():
    """FPDFTextObj_GetFontSize returns the unscaled text-space size (1.0 on real
    pages); the rendered size is the height of the object's bounds."""
    assert _span("Gambeson", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).size == 10.0


def test_span_keeps_the_whole_object_as_one_run():
    """Objects are atomic — the adapter must not pre-split or pre-group them."""
    assert _span("2 Armor Points", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).text == "2 Armor Points"


def test_span_normalises_internal_whitespace():
    assert _span("Find\tT raps ", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).text == "Find T raps"


def test_span_preserves_ligature_codepoints():
    """A ligature is one rendered glyph; dropping it corrupts words like 'find'."""
    assert _span("ﬁnd", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).text == "ﬁnd"


def test_span_reads_bold_from_weight_and_italic_from_angle():
    bold = _span("x", BOUNDS, PAGE_HEIGHT, "Serif", 700, 0)
    slanted = _span("x", BOUNDS, PAGE_HEIGHT, "Serif", 400, -12)
    assert (bold.bold, bold.italic) == (True, False)
    assert (slanted.bold, slanted.italic) == (False, True)


def test_span_is_none_for_empty_or_degenerate_objects():
    assert _span("   ", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0) is None
    assert _span("x", (10.0, 80.0, 10.0, 90.0), PAGE_HEIGHT, "Serif", 400, 0) is None


import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[2] / "evals" / "corpus.manifest.json"


def _corpus_pdf(doc_id: str) -> Path:
    if not MANIFEST.exists():
        pytest.skip("corpus manifest absent")
    doc = next(d for d in json.loads(MANIFEST.read_text())["documents"] if d["id"] == doc_id)
    path = MANIFEST.parent / "corpus" / doc["pdf"]["path"]
    if not path.exists():
        pytest.skip("corpus PDF absent")
    return path


def test_objects_carry_text_font_and_weight():
    """layout.py builds FontStats from these fields to classify headings; an
    adapter that leaves them empty cannot reach the reference."""
    import pypdfium2
    from ingest.pdfium_extract import _objects

    page = pypdfium2.PdfDocument(str(_corpus_pdf("osric_2e")))[155]
    spans = _objects(page, page.get_textpage())
    assert spans, "no text objects found on a text-bearing page"
    assert any(span.font for span in spans)
    assert any(span.bold for span in spans)
    assert all(span.size > 0 and span.text.strip() for span in spans)


def test_no_object_spans_two_columns_on_a_two_column_page():
    """The property the whole design rests on (Task 3 finding). OSRIC p.156 is
    a dense two-column page; its gutter sits near the page mid-line."""
    import pypdfium2
    from ingest.pdfium_extract import _objects

    page = pypdfium2.PdfDocument(str(_corpus_pdf("osric_2e")))[155]
    width = page.get_size()[0]
    straddlers = [s.text for s in _objects(page, page.get_textpage())
                  if s.bbox.x0 < width * 0.45 < s.bbox.x1 and s.bbox.x1 > width * 0.55]
    assert not straddlers, f"objects crossing the gutter: {straddlers[:5]}"


def test_rasterize_returns_rgb_pixels():
    from ingest.pdfium_extract import rasterize

    raster = rasterize(str(_corpus_pdf("cairn_1e")), 9, dpi=150)
    assert raster.ndim == 3 and raster.shape[2] == 3
    assert raster.dtype.name == "uint8"

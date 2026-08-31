"""Citations name the page a GM can find at the table.

TTRPG PDFs carry covers, front matter and ads, so the printed page number and
the PDF's own index routinely differ by 20-40 pages. When both are known the
printed one leads, with the physical page kept for PDF viewers.
"""
from mcp_server import _page_span


def test_printed_label_leads_with_the_physical_page_kept():
    assert _page_span({"page_start": 312, "page_end": 312,
                       "page_label_start": "276", "page_label_end": "276"}) == "p.276 (PDF p.312)"


def test_a_span_uses_both_printed_endpoints():
    assert _page_span({"page_start": 312, "page_end": 313,
                       "page_label_start": "276", "page_label_end": "277"}) == "pp.276–277 (PDF pp.312–313)"


def test_falls_back_to_physical_pages_when_the_pdf_has_no_labels():
    assert _page_span({"page_start": 12, "page_end": 12,
                       "page_label_start": "", "page_label_end": ""}) == "p.12"


def test_roman_front_matter_labels_survive():
    assert _page_span({"page_start": 2, "page_end": 2,
                       "page_label_start": "ii", "page_label_end": "ii"}) == "p.ii (PDF p.2)"


def test_no_span_at_all_when_pages_are_missing():
    assert _page_span({"page_start": 0, "page_end": 0}) == ""

"""Printed page labels — the number on the paper, not the PDF's page index.

TTRPG PDFs routinely carry covers, front matter and ads, so physical page 312
is often printed as 276. A citation a GM cannot find at the table is not a
citation, so the printed label travels with the chunk.
"""
import pymupdf
import pytest

from legend_lore.service import _embed_unit_metadata, _page_labels
from legend_lore.granularity import EmbedUnit


@pytest.fixture
def labelled_pdf(tmp_path):
    """Two roman front-matter pages, then decimal — physical 3 prints as '1'."""
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page()
    doc.set_page_labels([
        {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
        {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1},
    ])
    path = tmp_path / "labelled.pdf"
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def unlabelled_pdf(tmp_path):
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    path = tmp_path / "plain.pdf"
    doc.save(path)
    doc.close()
    return path


def test_page_labels_maps_physical_pages_to_printed_labels(labelled_pdf):
    assert _page_labels(labelled_pdf) == {1: "i", 2: "ii", 3: "1", 4: "2"}


def test_page_labels_omits_labels_that_match_the_physical_number(unlabelled_pdf):
    """A PDF with no /PageLabels reports its physical number; storing that
    would be noise, and consumers fall back to page_start anyway."""
    assert _page_labels(unlabelled_pdf) == {}


def _unit(page_start: int, page_end: int) -> EmbedUnit:
    return EmbedUnit(chunk_id="c1", text="t", parent_id="p1", chunk_type="prose",
                     section_heading="Combat", source_pdf="x.pdf",
                     page_start=page_start, page_end=page_end, ordinal=0)


def test_metadata_carries_the_printed_label_for_the_chunk_span(tmp_path):
    meta = _embed_unit_metadata(tmp_path / "x.pdf", _unit(3, 4), "osric",
                                {1: "i", 2: "ii", 3: "1", 4: "2"})
    assert meta["page_label_start"] == "1"
    assert meta["page_label_end"] == "2"


def test_metadata_leaves_labels_empty_when_the_pdf_has_none(tmp_path):
    meta = _embed_unit_metadata(tmp_path / "x.pdf", _unit(3, 4), "osric", {})
    assert meta["page_label_start"] == ""
    assert meta["page_label_end"] == ""

"""Metadata parity against the PyMuPDF reference on real corpus documents.
Skipped when the corpus is absent (it is gitignored)."""
import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[2] / "evals" / "corpus.manifest.json"


def _pdf(doc_id: str) -> Path:
    if not MANIFEST.exists():
        pytest.skip("corpus manifest absent")
    entry = json.loads(MANIFEST.read_text())
    doc = next(d for d in entry["documents"] if d["id"] == doc_id)
    path = MANIFEST.parent / "corpus" / doc["pdf"]["path"]
    if not path.exists():
        pytest.skip("corpus PDF absent")
    return path


@pytest.mark.parametrize("doc_id", ["osric_2e", "srd_5_1"])
def test_toc_matches_pymupdf(doc_id):
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import toc

    path = _pdf(doc_id)
    with pymupdf.open(str(path)) as doc:
        expected = tuple((lvl, title, page) for lvl, title, page in doc.get_toc())
    assert toc(pypdfium2.PdfDocument(str(path))) == expected


def test_toc_agrees_no_outline_for_document_without_one():
    """cairn_1e has no outline at all, so both libraries trivially return an
    empty TOC — a bare `() == ()` here would read as parity evidence while
    proving nothing beyond "does not crash". Assert explicitly that neither
    library found an outline, so the case documents *why* it is empty."""
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import toc

    path = _pdf("cairn_1e")
    with pymupdf.open(str(path)) as doc:
        assert doc.get_toc() == []
    assert toc(pypdfium2.PdfDocument(str(path))) == ()


@pytest.mark.parametrize("doc_id", ["osric_2e", "srd_5_1", "cairn_1e"])
def test_page_labels_match_pymupdf(doc_id):
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import page_labels

    path = _pdf(doc_id)
    with pymupdf.open(str(path)) as doc:
        expected = tuple(doc.load_page(i).get_label() or "" for i in range(doc.page_count))
    pdf = pypdfium2.PdfDocument(str(path))
    assert page_labels(pdf, len(pdf)) == expected


@pytest.mark.parametrize("doc_id,expected", [("osric_2e", "OSRIC"), ("cairn_1e", "Cairn")])
def test_title_reads_pdf_metadata(doc_id, expected):
    import pypdfium2
    from ingest.pdfium_meta import title

    path = _pdf(doc_id)
    assert title(pypdfium2.PdfDocument(str(path)), fallback="unused") == expected


def test_title_falls_back_when_pdf_has_no_title():
    """srd_5_1 has no /Title in its PDF metadata (confirmed against PyMuPDF
    below), so title() must return the caller-supplied fallback rather than
    an empty string."""
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import title

    path = _pdf("srd_5_1")
    with pymupdf.open(str(path)) as doc:
        assert not doc.metadata.get("title")
    assert title(pypdfium2.PdfDocument(str(path)), fallback="srd_5_1") == "srd_5_1"

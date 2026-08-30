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


@pytest.mark.parametrize("doc_id", ["osric_2e", "srd_5_1", "cairn_1e"])
def test_toc_matches_pymupdf(doc_id):
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import toc

    path = _pdf(doc_id)
    with pymupdf.open(str(path)) as doc:
        expected = tuple((lvl, title, page) for lvl, title, page in doc.get_toc())
    assert toc(pypdfium2.PdfDocument(str(path))) == expected


@pytest.mark.parametrize("doc_id", ["osric_2e", "srd_5_1"])
def test_page_labels_match_pymupdf(doc_id):
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import page_labels

    path = _pdf(doc_id)
    with pymupdf.open(str(path)) as doc:
        expected = tuple(doc.load_page(i).get_label() or "" for i in range(doc.page_count))
    pdf = pypdfium2.PdfDocument(str(path))
    assert page_labels(pdf, len(pdf)) == expected

"""
Tests for GET /api/section/{section_id} and GET /api/source/{filename}/pages.

These back the MCP drill-in tools (`get_section`, `get_pages`): compact
search hands the model a `section_id` or a page range instead of the full
section text, and these endpoints let it pull the full text on demand.

`/api/section/{id}` is exercised against a parents row staged directly in
the library store (the same technique test_search_sections.py uses) rather than a PDF run
through the real heading-detection pipeline — the plain-text fixture PDFs
in conftest.py produce no headings at all (`n_headings=0`), so a real
index of them never carries a resolvable `section_id`. `/pages` needs a
real file on disk (it opens the PDF with pymupdf), so it uses the
`sample_pdf_path` + `/api/index-files` pattern other endpoint tests use.
"""

import pytest

from legend_lore.granularity import ParentDoc

SOURCE = "/corpus/monsters.pdf"


def _parent(pid, heading, section_id, section_path, text, pages=(10, 10)):
    return ParentDoc(
        parent_id=pid,
        text=text,
        section_heading=heading,
        chunk_type="prose",
        source_pdf=SOURCE,
        page_start=pages[0],
        page_end=pages[1],
        section_id=section_id,
        section_path=section_path,
    )


@pytest.fixture
def section_client(client, test_store):
    """One staged section (`s_k`) in the library store `client` reads from."""
    test_store.replace_document(SOURCE, "unknown", (), [], [], [], parents=[
        _parent("p-k", "Monsters > Kraken", "s_k", "s_m/s_k",
                "Kraken. AC 18, HP 472. A gargantuan monstrosity."),
    ])
    return client


# ---------------------------------------------------------------------------
# GET /api/section/{section_id}
# ---------------------------------------------------------------------------

def test_get_section_returns_the_same_heading(section_client):
    response = section_client.get("/api/section/s_k")

    assert response.status_code == 200
    data = response.json()
    assert data["section_id"] == "s_k"
    assert data["section_heading"] == "Monsters > Kraken"
    assert data["filename"] == "monsters.pdf"
    assert data["source"] == SOURCE
    assert "gargantuan monstrosity" in data["text"]
    assert (data["page_start"], data["page_end"]) == (10, 10)


def test_get_section_container_id_assembles_the_chapter(section_client):
    """`s_m` owns no parents row — a heading immediately followed by a
    sub-heading emits no chunk — but it is the id search advertises for a
    Kraken hit, so the drill-in must resolve it."""
    response = section_client.get("/api/section/s_m")

    assert response.status_code == 200
    data = response.json()
    assert data["section_id"] == "s_m"
    assert "gargantuan monstrosity" in data["text"]
    # Whether what came back is the whole section or a window around the
    # match is something the caller has to be able to see.
    assert data["windowed"] is False


def test_get_section_unknown_id_404(section_client):
    response = section_client.get("/api/section/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/source/{filename}/pages
# ---------------------------------------------------------------------------

def _index(client, pdf_path):
    resp = client.post("/api/index-files", json={"paths": [str(pdf_path)]})
    assert resp.status_code == 200, resp.text


def test_get_pages_returns_the_first_pages_text(client, sample_pdf_path):
    _index(client, sample_pdf_path)

    response = client.get(
        "/api/source/dragonbane_monsters.pdf/pages",
        params={"start": 1, "end": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "dragonbane_monsters.pdf"
    assert data["start"] == 1
    assert data["end"] == 1
    assert "Fire Drake" in data["text"]


def test_get_pages_range_too_wide_is_400(client, sample_pdf_path):
    _index(client, sample_pdf_path)

    response = client.get(
        "/api/source/dragonbane_monsters.pdf/pages",
        params={"start": 1, "end": 25},
    )

    assert response.status_code == 400


def test_get_pages_span_caps_at_twenty_pages_inclusive(client, sample_pdf_path):
    """1–20 is twenty pages; 1–21 is twenty-one, one past the cap the
    MCP tool documents."""
    _index(client, sample_pdf_path)
    url = "/api/source/dragonbane_monsters.pdf/pages"

    assert client.get(url, params={"start": 1, "end": 20}).status_code == 200
    assert client.get(url, params={"start": 1, "end": 21}).status_code == 400


def test_get_pages_end_before_start_is_400(client, sample_pdf_path):
    _index(client, sample_pdf_path)

    response = client.get(
        "/api/source/dragonbane_monsters.pdf/pages",
        params={"start": 3, "end": 1},
    )

    assert response.status_code == 400


def test_get_pages_zero_start_is_422(client, sample_pdf_path):
    """Pages are 1-based. start=0 is a malformed request, not an inverted
    pair to be reasoned about downstream."""
    _index(client, sample_pdf_path)

    response = client.get(
        "/api/source/dragonbane_monsters.pdf/pages",
        params={"start": 0, "end": 0},
    )

    assert response.status_code == 422


def test_get_pages_unindexed_filename_404(client):
    response = client.get(
        "/api/source/nonexistent.pdf/pages",
        params={"start": 1, "end": 1},
    )

    assert response.status_code == 404


def test_get_pages_start_beyond_document_is_404(client, sample_pdf_path):
    """sample_pdf_path is a single-page PDF: a range starting past page 1
    must 404 with a page-count-aware message, not 200 with an inverted
    (lo > hi) pair and empty text."""
    _index(client, sample_pdf_path)

    response = client.get(
        "/api/source/dragonbane_monsters.pdf/pages",
        params={"start": 5, "end": 10},
    )

    assert response.status_code == 404
    assert "beyond the last page (1)" in response.json()["detail"]


def test_get_pages_end_beyond_document_is_clamped_and_reported(client, sample_pdf_path):
    """start is in range but end overshoots: clamp end to the document's
    last page, and say so in the response body (not just the text)."""
    _index(client, sample_pdf_path)

    response = client.get(
        "/api/source/dragonbane_monsters.pdf/pages",
        params={"start": 1, "end": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["start"] == 1
    assert data["end"] == 1

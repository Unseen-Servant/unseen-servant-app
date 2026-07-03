"""Scoping correctness for /api/search (issue #308).

Collection scoping and the secondary game-system clause both used to
filter by bare *filename*, so two same-named PDFs in different folders
(``/5e/Monster Manual.pdf`` vs ``/pf2e/Monster Manual.pdf`` — a case the
codebase explicitly supports elsewhere via path-hashed chunk IDs) leaked
into each other's scopes. Both clauses must filter by the exact source
path stored in chunk metadata.
"""

import pytest


def _make_pdf(path, marker: str) -> None:
    """Tiny one-page PDF whose text contains a distinguishing marker."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    text = c.beginText(72, 720)
    for line in (
        f"{marker} dragon bestiary",
        "The dragon guards its lair.",
        "Armor Class: 15",
    ):
        text.textLine(line)
    c.drawText(text)
    c.showPage()
    c.save()


@pytest.fixture
def twin_pdfs(tmp_path):
    """Two PDFs with the SAME filename in different folders."""
    a = tmp_path / "campaign" / "monsters.pdf"
    b = tmp_path / "other-system" / "monsters.pdf"
    _make_pdf(a, "alpha")
    _make_pdf(b, "beta")
    return a, b


def test_same_named_files_both_index(client, twin_pdfs):
    """Parent IDs must be path-unique: two same-named PDFs previously
    collided in the parents store (UNIQUE constraint on parent_id) and
    the second file failed to index at all."""
    a, b = twin_pdfs
    resp = client.post("/api/index-files", json={"paths": [str(a), str(b)]})
    assert resp.status_code == 200, resp.text

    resp = client.get("/api/sources")
    assert resp.status_code == 200
    sources = {s["source"]: s for s in resp.json()["sources"]}
    assert str(a) in sources and str(b) in sources
    assert sources[str(a)]["chunks"] > 0
    assert sources[str(b)]["chunks"] > 0


def test_collection_scope_excludes_same_named_file_outside_collection(
    client, twin_pdfs
):
    a, b = twin_pdfs
    client.post("/api/index-files", json={"paths": [str(a), str(b)]})
    resp = client.post("/api/collections", json={
        "name": "Campaign", "file_paths": [str(a)],
    })
    assert resp.status_code == 200, resp.text

    resp = client.post("/api/search", json={
        "query": "dragon", "n_results": 10, "rerank": False,
        "collection": "Campaign",
    })
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results, "in-collection twin must be findable"
    sources = {r["source"] for r in results}
    assert str(b) not in sources, (
        "same-named file outside the collection leaked into scoped search"
    )
    assert sources == {str(a)}


def test_secondary_game_system_scope_excludes_same_named_file(
    client, twin_pdfs
):
    """The secondary-tag fold-in must not pull in an untagged file that
    merely shares a filename with the tagged one."""
    a, b = twin_pdfs
    # Index and tag ONLY the first twin (set_game_systems is
    # filename-keyed, so tag before the same-named sibling exists).
    client.post("/api/index-files", json={"paths": [str(a)]})
    resp = client.post("/api/set-game-systems", json={
        "filename": a.name, "game_systems": ["Dragonbane", "D&D 5E"],
    })
    assert resp.status_code == 200, resp.text
    client.post("/api/index-files", json={"paths": [str(b)]})

    # "D&D 5E" is a's SECONDARY tag → served by the manifest fold-in
    # clause, not the primary chunk-metadata clause.
    resp = client.post("/api/search", json={
        "query": "dragon", "n_results": 10, "rerank": False,
        "game_system": "D&D 5E",
    })
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results, "the tagged twin must be findable via its secondary tag"
    sources = {r["source"] for r in results}
    assert str(b) not in sources, (
        "untagged same-named file leaked through the secondary-tag clause"
    )
    assert sources == {str(a)}


def test_collection_with_no_indexed_files_still_reports_cleanly(client, tmp_path):
    """Graceful-degradation path survives the switch to path filtering."""
    ghost = tmp_path / "never-indexed.pdf"
    resp = client.post("/api/collections", json={
        "name": "Ghosts", "file_paths": [str(ghost)],
    })
    assert resp.status_code == 200, resp.text

    resp = client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
        "collection": "Ghosts",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"] == []
    assert "no indexed files" in body.get("message", "").lower()

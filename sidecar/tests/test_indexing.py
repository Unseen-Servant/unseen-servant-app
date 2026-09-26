"""
Tests for POST /api/index-files.

This is the most important endpoint — it's the whole reason
the sidecar exists. These tests verify:
1. PDF text extraction works
2. Chunks are stored in the library store with correct metadata
3. Error handling for bad files
"""

from legend_lore.granularity import EmbedUnit
from legend_lore.library_store import LibraryStore


def _all_metadatas(store) -> list[dict]:
    """Every stored unit's metadata, as search reads it back."""
    ids = [r[0] for r in store.conn().execute("SELECT id FROM units")]
    return [u.metadata for u in store.hydrate(ids).values()]


def test_index_single_pdf(client, sample_pdf_path, test_store):
    """Indexing a valid PDF should return indexed=1 and store chunks."""
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["indexed"] == 1
    assert data["total"] == 1
    assert data["errors"] == []

    # Verify chunks were actually stored
    count = test_store.count_units()
    assert count > 0, "Expected chunks to be stored in the library store"


def test_index_stores_correct_metadata(client, sample_pdf_path, test_store):
    """Each chunk should carry the full metadata set: provenance, structural
    classification and page range."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    metadatas = _all_metadatas(test_store)
    assert metadatas, "Expected at least one chunk"
    for metadata in metadatas:
        # Provenance + system tagging
        assert "source" in metadata
        assert "filename" in metadata
        assert "chunk" in metadata
        assert "game_system" in metadata
        assert metadata["filename"] == "dragonbane_monsters.pdf"
        # Structural metadata from the structure-aware chunker
        assert metadata["chunk_type"] in {"prose", "table", "heading", "list", "mixed"}
        assert "section_heading" in metadata  # may be "" if before any heading
        assert isinstance(metadata["page_start"], int)
        assert isinstance(metadata["page_end"], int)
        assert metadata["page_start"] >= 1
        assert metadata["page_end"] >= metadata["page_start"]
        # Parent-document retrieval (#146): every embed unit points at a parent
        assert "parent_id" in metadata
        assert metadata["parent_id"].startswith("p_")
        # Section identity (roadmap 1.3): every embed unit carries its section
        # (this fixture's plain-text PDF yields no markdown headings, so
        # both fields may legitimately be "" — same tolerance as
        # section_heading above)
        assert "section_id" in metadata
        assert "section_path" in metadata
        if metadata["section_id"]:
            assert metadata["section_id"].startswith("s_")
        if metadata["section_path"]:
            assert "/" in metadata["section_path"] or metadata["section_path"].startswith("s_")


def _stored_metadata(tmp_path, eu: EmbedUnit) -> dict:
    """Round-trip one unit through the library store."""
    store = LibraryStore.open(tmp_path / "library.sqlite3", "m", 2)
    store.replace_document("x.pdf", "5e", (), [eu], ["t"], [[1.0, 0.0]], [])
    (uid, _), = store.knn([1.0, 0.0], k=1)
    meta = store.hydrate([uid])[uid].metadata
    store.close()
    return meta


def test_stored_metadata_carries_section_identity(tmp_path):
    """Direct check on the field mapping (the sample PDF fixture has no
    real headings, so the endpoint-level test above can't exercise a
    populated section_id/section_path)."""
    eu = EmbedUnit(
        chunk_id="c1", text="t", parent_id="p_1", chunk_type="prose",
        section_heading="Monsters > Kraken", source_pdf="x.pdf",
        page_start=1, page_end=1, ordinal=0,
        section_id="s_abc123", section_path="s_111/s_abc123",
    )
    meta = _stored_metadata(tmp_path, eu)
    assert meta["section_id"] == "s_abc123"
    assert meta["section_path"] == "s_111/s_abc123"


def test_stored_metadata_section_identity_defaults_to_empty_string(tmp_path):
    eu = EmbedUnit(
        chunk_id="c1", text="t", parent_id="p_1", chunk_type="prose",
        section_heading=None, source_pdf="x.pdf",
        page_start=1, page_end=1, ordinal=0,
    )
    meta = _stored_metadata(tmp_path, eu)
    assert meta["section_id"] == ""
    assert meta["section_path"] == ""


def test_index_missing_file(client):
    """Indexing a file that doesn't exist should report an error, not crash."""
    response = client.post("/api/index-files", json={
        "paths": ["/nonexistent/fake_module.pdf"]
    })

    assert response.status_code == 200  # The endpoint itself succeeds
    data = response.json()
    assert data["indexed"] == 0
    assert data["total"] == 1
    assert len(data["errors"]) == 1
    assert "File not found" in data["errors"][0]


def test_index_empty_pdf(client, empty_pdf_path):
    """A PDF with no extractable text should be reported as an error."""
    response = client.post("/api/index-files", json={
        "paths": [str(empty_pdf_path)]
    })

    data = response.json()
    assert data["indexed"] == 0
    assert len(data["errors"]) == 1
    assert "Empty or scanned PDF" in data["errors"][0]


def test_index_multiple_pdfs(client, sample_pdf_path, large_text_pdf_path):
    """Indexing multiple files in one request."""
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })

    data = response.json()
    assert data["indexed"] == 2
    assert data["total"] == 2
    assert data["errors"] == []


def test_index_mixed_valid_and_invalid(client, sample_pdf_path):
    """Mix of valid and invalid paths: valid ones should still be indexed."""
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), "/nonexistent/nope.pdf"]
    })

    data = response.json()
    assert data["indexed"] == 1
    assert data["total"] == 2
    assert len(data["errors"]) == 1


def test_index_large_pdf_creates_multiple_chunks(
    client, large_text_pdf_path, test_store
):
    """A PDF with > 1000 chars should produce multiple chunks.

    For your 18GB collection, some PDFs will have thousands of chunks.
    This verifies the batching logic works correctly.
    """
    client.post("/api/index-files", json={
        "paths": [str(large_text_pdf_path)]
    })

    count = test_store.count_units()
    assert count > 1, f"Expected multiple chunks, got {count}"


def test_index_empty_paths_list(client):
    """Sending an empty list should return indexed=0 with no errors."""
    response = client.post("/api/index-files", json={
        "paths": []
    })

    data = response.json()
    assert data["indexed"] == 0
    assert data["total"] == 0
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# Game system metadata
# ---------------------------------------------------------------------------

def test_index_stores_game_system_metadata(
    client, dnd5e_pdf_path, test_store
):
    """Chunks from a D&D 5E folder should have game_system in metadata."""
    client.post("/api/index-files", json={
        "paths": [str(dnd5e_pdf_path)]
    })

    metadatas = _all_metadatas(test_store)
    assert metadatas
    for metadata in metadatas:
        assert metadata["game_system"] == "D&D 5E"


def test_index_unknown_game_system(client, untagged_pdf_path, test_store):
    """PDF with no system hints should get game_system='unknown'."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    metadatas = _all_metadatas(test_store)
    assert metadatas
    for metadata in metadatas:
        assert metadata["game_system"] == "unknown"


def test_index_with_game_system_override(
    client, untagged_pdf_path, test_store
):
    """Manual game_system override should take priority over detection."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)],
        "game_system": "Savage Worlds",
    })

    metadatas = _all_metadatas(test_store)
    assert metadatas
    for metadata in metadatas:
        assert metadata["game_system"] == "Savage Worlds"


# ---------------------------------------------------------------------------
# Disk space: legacy Chroma cleanup and delete-index
# (moved from test_orphan_gc.py when Compact and the orphan GC were removed)
# ---------------------------------------------------------------------------

FAKE_UUID = "deadbeef-1234-5678-90ab-cdef12345678"
NOT_A_UUID = "some-other-folder"


def test_uuid_dir_re_matches_chroma_format():
    from legend_lore.service import _UUID_DIR_RE

    assert _UUID_DIR_RE.match("a2e2e402-4607-40e8-94ad-c92b42f0d3e4")
    assert _UUID_DIR_RE.match(FAKE_UUID)
    assert not _UUID_DIR_RE.match("not-a-uuid")
    assert not _UUID_DIR_RE.match("a2e2e402-4607-40e8-94ad-c92b42f0d3e")  # short
    assert not _UUID_DIR_RE.match("../etc/passwd")


def test_remove_legacy_chroma_deletes_old_store_and_keeps_the_rest(tmp_path):
    """Boot cleanup removes chroma.sqlite3 (+ sidecar files), parents.sqlite3
    and Chroma's UUID segment dirs; anything else in the data dir survives."""
    from legend_lore.service import remove_legacy_chroma

    (tmp_path / "chroma.sqlite3").write_bytes(b"c" * 1000)
    (tmp_path / "chroma.sqlite3-wal").write_bytes(b"w" * 10)
    (tmp_path / "parents.sqlite3").write_bytes(b"p" * 500)
    seg = tmp_path / FAKE_UUID
    seg.mkdir()
    (seg / "data_level0.bin").write_bytes(b"x" * 4096)
    keep = tmp_path / NOT_A_UUID
    keep.mkdir()
    (keep / "important.txt").write_text("don't delete me")
    (tmp_path / "library.sqlite3").write_bytes(b"l")
    (tmp_path / "index_manifest.json").write_text("{}")

    freed = remove_legacy_chroma(tmp_path)

    assert freed == 1000 + 10 + 500 + 4096
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "index_manifest.json", "library.sqlite3", NOT_A_UUID,
    ]
    assert (keep / "important.txt").read_text() == "don't delete me"
    assert remove_legacy_chroma(tmp_path) == 0  # idempotent


def test_delete_index_shrinks_the_store_file(client, test_store, large_text_pdf_path):
    """Delete-index returns the space to disk (VACUUM) — no Compact step."""
    # Page count, not file size: in WAL mode the main file lags until a
    # checkpoint.
    def pages():
        return test_store.conn().execute("PRAGMA page_count").fetchone()[0]

    client.post("/api/index-files", json={"paths": [str(large_text_pdf_path)]})
    pages_indexed = pages()

    response = client.post("/api/delete-index")

    assert response.status_code == 200
    assert response.json()["removed_chunks"] > 0
    assert test_store.count_units() == 0
    assert pages() < pages_indexed
    assert test_store.conn().execute("PRAGMA freelist_count").fetchone()[0] == 0

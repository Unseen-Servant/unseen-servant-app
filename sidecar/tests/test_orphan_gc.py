"""Tests for orphaned HNSW segment dir cleanup.

Background: ``chromadb.Client.delete_collection`` only removes metadata
rows in ``chroma.sqlite3``; the on-disk segment directories are left
behind. This module covers the GC helpers and their endpoint integrations.
"""

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from fastapi.testclient import TestClient
import pytest

from legend_lore.granularity import ParentDoc
from legend_lore.parents_store import upsert_parents, clear_all_parents
from legend_lore.service import (
    _UUID_DIR_RE,
    _compute_reclaimable_bytes,
    _live_segment_ids,
    _orphan_segment_bytes,
    _segment_ids_for_collection,
    _sqlite_freelist_bytes,
    _remove_segment_dir,
    compact_sqlite,
    gc_orphan_segments,
)
from server import create_app


FAKE_UUID = "deadbeef-1234-5678-90ab-cdef12345678"
NOT_A_UUID = "some-other-folder"


# ---------------------------------------------------------------------------
# Fixtures: persistent Chroma backed by tmp_path (real on-disk segment dirs)
# ---------------------------------------------------------------------------

@pytest.fixture
def persistent_setup(tmp_path):
    """Persistent Chroma client + collection in ``tmp_path``.

    Unlike the conftest's EphemeralClient fixture, this writes real segment
    directories to disk so the GC paths are actually exercised.
    """
    client = chromadb.PersistentClient(path=str(tmp_path))
    embed_fn = DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name="ttrpg_docs", embedding_function=embed_fn
    )
    collection.add(
        ids=["seed-0"],
        documents=["seed document so the segment dir materializes"],
    )
    return tmp_path, client, collection, embed_fn


def _uuid_dirs(data_dir):
    return [p for p in data_dir.iterdir() if p.is_dir() and _UUID_DIR_RE.match(p.name)]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_uuid_dir_re_matches_chroma_format():
    assert _UUID_DIR_RE.match("a2e2e402-4607-40e8-94ad-c92b42f0d3e4")
    assert _UUID_DIR_RE.match(FAKE_UUID)
    assert not _UUID_DIR_RE.match("not-a-uuid")
    assert not _UUID_DIR_RE.match("a2e2e402-4607-40e8-94ad-c92b42f0d3e")  # short
    assert not _UUID_DIR_RE.match("../etc/passwd")


def test_live_segment_ids_returns_set_from_sqlite(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    live = _live_segment_ids(data_dir)
    assert isinstance(live, set)
    assert len(live) >= 1
    on_disk = {d.name for d in _uuid_dirs(data_dir)}
    # Every on-disk UUID dir should be a live segment.
    assert on_disk.issubset(live)


def test_live_segment_ids_handles_missing_sqlite(tmp_path):
    assert _live_segment_ids(tmp_path) == set()


def test_segment_ids_for_collection_returns_uuids(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    ids = _segment_ids_for_collection(data_dir, "ttrpg_docs")
    assert ids
    assert all(_UUID_DIR_RE.match(sid) for sid in ids)


def test_segment_ids_for_unknown_collection_is_empty(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    assert _segment_ids_for_collection(data_dir, "no_such_collection") == []


def test_remove_segment_dir_skips_non_uuid_names(tmp_path):
    safe_dir = tmp_path / NOT_A_UUID
    safe_dir.mkdir()
    (safe_dir / "important.txt").write_text("don't delete me")

    reclaimed = _remove_segment_dir(tmp_path, NOT_A_UUID)
    assert reclaimed == 0
    assert safe_dir.exists()


def test_remove_segment_dir_removes_uuid_named_dir(tmp_path):
    fake = tmp_path / FAKE_UUID
    fake.mkdir()
    (fake / "data_level0.bin").write_bytes(b"x" * 1024)

    reclaimed = _remove_segment_dir(tmp_path, FAKE_UUID)
    assert reclaimed >= 1024
    assert not fake.exists()


# ---------------------------------------------------------------------------
# gc_orphan_segments
# ---------------------------------------------------------------------------

def test_gc_orphan_segments_removes_orphan_dirs(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    real_dirs = {d.name for d in _uuid_dirs(data_dir)}
    assert real_dirs

    fake = data_dir / FAKE_UUID
    fake.mkdir()
    (fake / "data_level0.bin").write_bytes(b"x" * 4096)

    reclaimed = gc_orphan_segments(data_dir)
    assert reclaimed >= 4096

    assert not fake.exists(), "Orphan dir should have been removed"
    surviving = {d.name for d in _uuid_dirs(data_dir)}
    assert surviving == real_dirs


def test_gc_orphan_segments_preserves_non_uuid_dirs(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    other = data_dir / NOT_A_UUID
    other.mkdir()
    (other / "keep").write_text("important")

    gc_orphan_segments(data_dir)
    assert other.exists()
    assert (other / "keep").read_text() == "important"


def test_gc_orphan_segments_handles_missing_data_dir(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert gc_orphan_segments(missing) == 0


def test_gc_orphan_segments_handles_fresh_install(tmp_path):
    # No chroma.sqlite3 yet — fresh install case.
    assert gc_orphan_segments(tmp_path) == 0


def test_gc_orphan_segments_idempotent(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    fake = data_dir / FAKE_UUID
    fake.mkdir()
    (fake / "data_level0.bin").write_bytes(b"y" * 2048)

    first = gc_orphan_segments(data_dir)
    second = gc_orphan_segments(data_dir)
    assert first >= 2048
    assert second == 0


# ---------------------------------------------------------------------------
# Endpoint integration: delete-index removes the segment dir
# ---------------------------------------------------------------------------

def test_delete_index_removes_old_segment_dir(persistent_setup):
    data_dir, chroma_client, collection, embed_fn = persistent_setup
    app = create_app(
        collection=collection,
        data_dir=data_dir,
        chroma_client=chroma_client,
        embedding_function=embed_fn,
    )
    test_client = TestClient(app)

    old_segment_dirs = {d.name for d in _uuid_dirs(data_dir)}
    assert old_segment_dirs, "Setup should have produced at least one segment dir"

    response = test_client.post("/api/delete-index")
    assert response.status_code == 200

    surviving = {d.name for d in _uuid_dirs(data_dir)}
    leaked = surviving & old_segment_dirs
    assert not leaked, f"Delete-index leaked segment dirs: {leaked}"


def test_compact_sqlite_vacuums_parents_store(tmp_path):
    """compact_sqlite should reclaim tombstoned pages from parents.sqlite3
    too — not just chroma.sqlite3. clear_all_parents leaves the file sized
    by its previous high-water mark until VACUUM runs.
    """
    parents = [
        ParentDoc(
            parent_id=f"p_{i}",
            text="x" * 4000,
            section_heading=f"Section {i}",
            chunk_type="prose",
            source_pdf="big.pdf",
            page_start=i,
            page_end=i,
        )
        for i in range(500)
    ]
    upsert_parents(tmp_path, "/path/to/big.pdf", parents)
    bloated = (tmp_path / "parents.sqlite3").stat().st_size
    clear_all_parents(tmp_path)
    after_clear = (tmp_path / "parents.sqlite3").stat().st_size
    # Without VACUUM, deleted rows leave the file at its high-water mark.
    assert after_clear >= bloated * 0.5, (
        "Sanity check: clear_all_parents alone should NOT shrink the file"
    )

    reclaimed = compact_sqlite(tmp_path)
    after_compact = (tmp_path / "parents.sqlite3").stat().st_size
    assert reclaimed > 0
    assert after_compact < after_clear


def test_compact_sqlite_handles_missing_files(tmp_path):
    # No databases yet — should be a no-op without raising.
    assert compact_sqlite(tmp_path) == 0


def test_reclaimable_bytes_sums_all_sources(tmp_path):
    """``/api/stats`` should report freelist from BOTH sqlite stores plus any
    orphan segment dirs — that's the set of bytes a Compact would actually
    recover. Pre-fix, only chroma.sqlite3 was counted, so the UI hid the
    Compact button whenever the user only had parents-store churn or
    orphan dirs.
    """
    parents = [
        ParentDoc(
            parent_id=f"p_{i}",
            text="x" * 4000,
            section_heading=f"S{i}",
            chunk_type="prose",
            source_pdf="big.pdf",
            page_start=i,
            page_end=i,
        )
        for i in range(500)
    ]
    upsert_parents(tmp_path, "/path/to/big.pdf", parents)
    clear_all_parents(tmp_path)
    parents_freelist = _sqlite_freelist_bytes(tmp_path / "parents.sqlite3")
    assert parents_freelist > 0, "Setup should leave reclaimable pages"

    fake = tmp_path / FAKE_UUID
    fake.mkdir()
    (fake / "data_level0.bin").write_bytes(b"q" * 12_345)

    reclaimable = _compute_reclaimable_bytes(tmp_path)
    assert reclaimable >= parents_freelist + 12_345


def test_reclaimable_bytes_zero_when_clean(tmp_path):
    assert _compute_reclaimable_bytes(tmp_path) == 0


def test_orphan_segment_bytes_only_counts_orphans(persistent_setup):
    data_dir, _, _, _ = persistent_setup
    assert _orphan_segment_bytes(data_dir) == 0  # only live segments
    fake = data_dir / FAKE_UUID
    fake.mkdir()
    (fake / "data_level0.bin").write_bytes(b"r" * 9_000)
    assert _orphan_segment_bytes(data_dir) >= 9_000


def test_stats_endpoint_reports_combined_reclaimable(tmp_path):
    """End-to-end: /api/stats reflects the sum across all sources."""
    client = chromadb.PersistentClient(path=str(tmp_path))
    embed_fn = DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name="ttrpg_docs", embedding_function=embed_fn
    )
    collection.add(
        ids=["seed-0"],
        documents=["seed"],
        metadatas=[{"filename": "x.pdf"}],
    )

    parents = [
        ParentDoc(
            parent_id=f"p_{i}", text="y" * 4000, section_heading=None,
            chunk_type="prose", source_pdf="x.pdf", page_start=i, page_end=i,
        )
        for i in range(200)
    ]
    upsert_parents(tmp_path, "/x.pdf", parents)
    clear_all_parents(tmp_path)

    app = create_app(
        collection=collection, data_dir=tmp_path,
        chroma_client=client, embedding_function=embed_fn,
    )
    test_client = TestClient(app)
    body = test_client.get("/api/stats").json()
    assert body["reclaimable_bytes"] >= _sqlite_freelist_bytes(tmp_path / "parents.sqlite3")
    assert body["reclaimable_bytes"] > 0


def test_compact_endpoint_runs_orphan_gc(persistent_setup):
    data_dir, chroma_client, collection, embed_fn = persistent_setup
    app = create_app(
        collection=collection,
        data_dir=data_dir,
        chroma_client=chroma_client,
        embedding_function=embed_fn,
    )
    test_client = TestClient(app)

    fake = data_dir / FAKE_UUID
    fake.mkdir()
    (fake / "data_level0.bin").write_bytes(b"z" * 8192)

    response = test_client.post("/api/compact")
    assert response.status_code == 200
    body = response.json()
    assert body["reclaimed"] >= 8192
    assert not fake.exists()

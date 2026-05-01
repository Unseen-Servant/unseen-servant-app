"""
Tests for the library-health audit endpoint.

Library health derives four sections from existing state:
- orphans: indexed files in no collection
- anchors: files in 3+ (non-archived) collections
- overlap: pairwise intersections between non-archived collections
- stale: all non-archived collections sorted by last_used_at asc

No precompute, no logging — pure read.
"""

from server import MANIFEST_FILENAME, IndexManifest, ManifestEntry


def _seed_manifest(tmp_path, paths_with_filenames):
    """Write a manifest with the given paths. Returns the manifest."""
    files = {}
    for path, filename in paths_with_filenames:
        files[path] = ManifestEntry(
            filename=filename,
            mtime=1000.0,
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            game_system="D&D 5E",
            file_size=1024,
        )
    manifest = IndexManifest(files=files)
    (tmp_path / MANIFEST_FILENAME).write_text(manifest.model_dump_json())
    return manifest


# ---------------------------------------------------------------------------
# Empty / sparse cases
# ---------------------------------------------------------------------------

def test_empty_store(client):
    """Empty manifest and no collections — every section is empty."""
    resp = client.get("/api/library-health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["orphans"] == []
    assert data["anchors"] == []
    assert data["overlap"] == []
    assert data["stale"] == []


def test_orphans_when_no_collections(client, tmp_path):
    """Indexed files with zero collections are all orphans."""
    _seed_manifest(tmp_path, [
        ("/a.pdf", "a.pdf"),
        ("/b.pdf", "b.pdf"),
    ])
    data = client.get("/api/library-health").json()
    assert {o["path"] for o in data["orphans"]} == {"/a.pdf", "/b.pdf"}
    assert data["anchors"] == []
    assert data["overlap"] == []


# ---------------------------------------------------------------------------
# Orphans
# ---------------------------------------------------------------------------

def test_orphan_detection_excludes_files_in_any_collection(client, tmp_path):
    """A file in any collection (even archived) is not an orphan."""
    _seed_manifest(tmp_path, [
        ("/a.pdf", "a.pdf"),
        ("/b.pdf", "b.pdf"),
        ("/c.pdf", "c.pdf"),
    ])
    client.post("/api/collections", json={"name": "X", "file_paths": ["/a.pdf"]})
    # Archived collection still "owns" /b.pdf — it's not an orphan
    client.post("/api/collections", json={"name": "Y", "file_paths": ["/b.pdf"]})
    client.put("/api/collections/Y", json={"archived": True})

    data = client.get("/api/library-health").json()
    paths = {o["path"] for o in data["orphans"]}
    assert paths == {"/c.pdf"}


def test_orphans_carry_metadata(client, tmp_path):
    """Orphan rows include filename, game_system, size."""
    _seed_manifest(tmp_path, [("/lonely.pdf", "lonely.pdf")])
    data = client.get("/api/library-health").json()
    assert len(data["orphans"]) == 1
    orphan = data["orphans"][0]
    assert orphan["filename"] == "lonely.pdf"
    assert orphan["game_system"] == "D&D 5E"
    assert orphan["size_bytes"] == 1024


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

def test_anchors_threshold_is_three(client, tmp_path):
    """A file in 2 collections is not an anchor; 3+ is."""
    _seed_manifest(tmp_path, [
        ("/p.pdf", "p.pdf"),
        ("/q.pdf", "q.pdf"),
    ])
    # /p.pdf in 3 collections, /q.pdf in 2
    client.post("/api/collections", json={"name": "A", "file_paths": ["/p.pdf", "/q.pdf"]})
    client.post("/api/collections", json={"name": "B", "file_paths": ["/p.pdf", "/q.pdf"]})
    client.post("/api/collections", json={"name": "C", "file_paths": ["/p.pdf"]})

    data = client.get("/api/library-health").json()
    assert len(data["anchors"]) == 1
    anchor = data["anchors"][0]
    assert anchor["path"] == "/p.pdf"
    assert anchor["count"] == 3
    assert anchor["collections"] == ["A", "B", "C"]


def test_anchors_exclude_archived_collections(client, tmp_path):
    """Archived collections do not contribute to anchor counts."""
    _seed_manifest(tmp_path, [("/p.pdf", "p.pdf")])
    client.post("/api/collections", json={"name": "A", "file_paths": ["/p.pdf"]})
    client.post("/api/collections", json={"name": "B", "file_paths": ["/p.pdf"]})
    client.post("/api/collections", json={"name": "C", "file_paths": ["/p.pdf"]})
    # Archive C → /p.pdf now in 2 active collections, no longer an anchor
    client.put("/api/collections/C", json={"archived": True})

    data = client.get("/api/library-health").json()
    assert data["anchors"] == []


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------

def test_overlap_lists_only_pairs_with_shared_files(client, tmp_path):
    """Pairs with zero overlap are omitted; the rest sorted by count desc."""
    _seed_manifest(tmp_path, [
        ("/a.pdf", "a.pdf"),
        ("/b.pdf", "b.pdf"),
        ("/c.pdf", "c.pdf"),
    ])
    client.post("/api/collections", json={"name": "X", "file_paths": ["/a.pdf", "/b.pdf"]})
    client.post("/api/collections", json={"name": "Y", "file_paths": ["/a.pdf", "/b.pdf", "/c.pdf"]})
    client.post("/api/collections", json={"name": "Z", "file_paths": ["/c.pdf"]})

    data = client.get("/api/library-health").json()
    pairs = [(o["a"], o["b"], o["count"]) for o in data["overlap"]]
    # X ∩ Y = {/a.pdf, /b.pdf} = 2; Y ∩ Z = {/c.pdf} = 1; X ∩ Z = ∅
    assert pairs[0] == ("X", "Y", 2)
    assert ("Y", "Z", 1) in pairs
    assert all(p[2] > 0 for p in pairs)
    assert len(pairs) == 2


def test_overlap_excludes_archived(client, tmp_path):
    """Archived collections are not paired in overlap."""
    _seed_manifest(tmp_path, [("/a.pdf", "a.pdf")])
    client.post("/api/collections", json={"name": "X", "file_paths": ["/a.pdf"]})
    client.post("/api/collections", json={"name": "Y", "file_paths": ["/a.pdf"]})
    client.put("/api/collections/Y", json={"archived": True})

    data = client.get("/api/library-health").json()
    assert data["overlap"] == []


# ---------------------------------------------------------------------------
# Stale
# ---------------------------------------------------------------------------

def test_stale_returns_all_non_archived_collections_sorted(client, tmp_path):
    """Stale list includes non-archived collections, nulls first then asc by date."""
    _seed_manifest(tmp_path, [])
    client.post("/api/collections", json={"name": "Recent", "file_paths": []})
    client.post("/api/collections", json={"name": "Older", "file_paths": []})
    client.post("/api/collections", json={"name": "Never", "file_paths": []})
    client.put("/api/collections/Recent", json={"last_used_at": "2026-04-30T00:00:00+00:00"})
    client.put("/api/collections/Older", json={"last_used_at": "2026-01-01T00:00:00+00:00"})

    data = client.get("/api/library-health").json()
    names = [s["name"] for s in data["stale"]]
    # Nulls first (Never), then ascending real timestamps (Older, then Recent)
    assert names == ["Never", "Older", "Recent"]
    assert data["stale"][0]["last_used_at"] is None


def test_stale_excludes_archived(client, tmp_path):
    """Archived collections are not in the stale list."""
    _seed_manifest(tmp_path, [])
    client.post("/api/collections", json={"name": "Active", "file_paths": []})
    client.post("/api/collections", json={"name": "Buried", "file_paths": []})
    client.put("/api/collections/Buried", json={"archived": True})

    data = client.get("/api/library-health").json()
    assert {s["name"] for s in data["stale"]} == {"Active"}

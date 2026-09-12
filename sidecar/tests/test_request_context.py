"""One read of each per-request file per search (#343).

A single ``/api/search`` used to re-read ``index_manifest.json`` up to
four times — once for a collection scope, once for the
``source_filter``/``game_system`` fuzzy resolution, once for the
secondary game-system tags, and once more inside
``_system_boost_factors`` — on top of ``collections.json`` and
``search_settings.json``. On a large library that is several megabytes
of JSON parsed per keystroke-driven search. They are now read once into
a ``RequestContext`` at the top of ``_search_sync``.
"""

import pytest

import server
from parents_store import upsert_units_fts
from server import (
    Collection,
    CollectionsStore,
    IndexManifest,
    ManifestEntry,
    manifest_digest,
    save_collections,
    save_manifest,
)


def _entry(filename: str, game_system: str = "OSR", content_hash: str = "h1",
           pipeline_version: str = "p1") -> ManifestEntry:
    return ManifestEntry(
        filename=filename,
        mtime=1.0,
        chunk_count=1,
        indexed_at="2026-09-12T00:00:00+00:00",
        game_system=game_system,
        content_hash=content_hash,
        pipeline_version=pipeline_version,
    )


# ---------------------------------------------------------------------------
# manifest_digest (unit)
# ---------------------------------------------------------------------------

def test_manifest_digest_is_order_independent():
    """Two manifests with the same files in a different insertion order
    describe the same index — the digest must agree, or a cache keyed on
    it would rebuild after every manifest rewrite."""
    a = IndexManifest(files={"/a.pdf": _entry("a.pdf"), "/b.pdf": _entry("b.pdf")})
    b = IndexManifest(files={"/b.pdf": _entry("b.pdf"), "/a.pdf": _entry("a.pdf")})
    assert manifest_digest(a) == manifest_digest(b)


def test_manifest_digest_changes_when_a_content_hash_changes():
    """A re-indexed file keeps its path — the digest must still move."""
    before = IndexManifest(files={"/a.pdf": _entry("a.pdf", content_hash="h1")})
    after = IndexManifest(files={"/a.pdf": _entry("a.pdf", content_hash="h2")})
    assert manifest_digest(before) != manifest_digest(after)


def test_manifest_digest_changes_on_add_remove_and_pipeline_version():
    one = IndexManifest(files={"/a.pdf": _entry("a.pdf")})
    two = IndexManifest(files={"/a.pdf": _entry("a.pdf"), "/b.pdf": _entry("b.pdf")})
    repipelined = IndexManifest(
        files={"/a.pdf": _entry("a.pdf", pipeline_version="p2")}
    )
    assert manifest_digest(one) != manifest_digest(two)
    assert manifest_digest(one) != manifest_digest(repipelined)
    assert manifest_digest(IndexManifest()) == manifest_digest(IndexManifest())


# ---------------------------------------------------------------------------
# /api/search — one load per file per request
# ---------------------------------------------------------------------------

def _meta(parent_id: str, filename: str, game_system: str) -> dict:
    return {
        "parent_id": parent_id,
        "filename": filename,
        "source": f"/corpus/{filename}",
        "game_system": game_system,
        "section_heading": "",
        "page_start": 1,
        "page_end": 1,
    }


FAKE_RESULTS = {
    "ids": [["c-osr", "c-srd"]],
    "documents": [["osr fireball text", "srd fireball text"]],
    "metadatas": [[
        _meta("p-osr", "monsters.pdf", "OSR"),
        _meta("p-srd", "SRD_CC_v5.1.pdf", "D&D 5E"),
    ]],
    "distances": [[0.10, 0.30]],
}

MANIFEST = IndexManifest(files={
    "/corpus/monsters.pdf": _entry("monsters.pdf", "OSR"),
    "/corpus/SRD_CC_v5.1.pdf": _entry("SRD_CC_v5.1.pdf", "D&D 5E"),
})


@pytest.fixture
def counting_loads(monkeypatch):
    """Count real loads of the manifest and the collections store."""
    counts = {"manifest": 0, "collections": 0}
    real_manifest = server.load_manifest
    real_collections = server.load_collections

    def count_manifest(data_dir):
        counts["manifest"] += 1
        return real_manifest(data_dir)

    def count_collections(data_dir):
        counts["collections"] += 1
        return real_collections(data_dir)

    monkeypatch.setattr(server, "load_manifest", count_manifest)
    monkeypatch.setattr(server, "load_collections", count_collections)
    return counts


@pytest.fixture
def fake_pool_client(client, test_collection, tmp_path, monkeypatch):
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: FAKE_RESULTS)
    save_manifest(tmp_path, MANIFEST)
    # FTS rows covering every indexed chunk, as in any index built since
    # roadmap 1.6 — so the spell corrector takes its manifest-digest,
    # store-backed path and must reuse the request's manifest rather than
    # reading its own.
    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-osr", 0, "monsters.pdf", "OSR", "p-osr", "osr fireball text")])
    upsert_units_fts(tmp_path, "/corpus/SRD_CC_v5.1.pdf", [
        ("c-srd", 0, "SRD_CC_v5.1.pdf", "D&D 5E", "p-srd", "srd fireball text")])
    return client


def _search(client, **overrides):
    payload = {"query": "fireball damage", "n_results": 5, "rerank": False,
               **overrides}
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_search_reads_manifest_once(fake_pool_client, counting_loads):
    """source_filter + game_system each used to trigger their own read
    (fuzzy resolution, then the secondary-tag scan)."""
    body = _search(
        fake_pool_client, source_filter="monsters", game_system="osr")
    assert body["results"]
    # Both near-misses still resolve — the shared manifest is the real one.
    assert 'source_filter "monsters" matched "monsters.pdf".' in body["message"]
    assert 'game_system "osr" matched "OSR".' in body["message"]
    assert counting_loads["manifest"] == 1


def test_boosted_search_reads_manifest_once(fake_pool_client, counting_loads):
    """The unfiltered path reads it for the game-system soft boost."""
    body = _search(fake_pool_client, query="Fireball damage in 5E SRD")
    # The boost still promotes the matching system (ordering unchanged).
    assert [r["filename"] for r in body["results"]] == [
        "SRD_CC_v5.1.pdf", "monsters.pdf"]
    assert counting_loads["manifest"] == 1


def test_collection_search_reads_each_store_once(
    fake_pool_client, tmp_path, counting_loads
):
    save_collections(tmp_path, CollectionsStore(collections={"osr night": Collection(
        id="c1",
        name="osr night",
        file_paths=["/corpus/monsters.pdf"],
        created_at="2026-09-12T00:00:00+00:00",
        updated_at="2026-09-12T00:00:00+00:00",
    )}))
    body = _search(fake_pool_client, collection="osr night")
    assert body["effective_collection"] == "osr night"
    assert counting_loads["manifest"] == 1
    assert counting_loads["collections"] == 1

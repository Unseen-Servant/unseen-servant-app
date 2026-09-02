"""Library tier: docs pinned by SHA-256, resolved through a v2 index manifest,
never indexed by the harness (roadmap 2026-09-02 Phase 0.4)."""
import hashlib
import json

import pytest

from evals import library


def _manifest(tmp_path, files: dict[str, bytes]) -> dict:
    """Write PDFs (any bytes) + a v2-shaped index_manifest.json; return its files dict."""
    entries = {}
    for name, data in files.items():
        p = tmp_path / name
        p.write_bytes(data)
        entries[str(p)] = {"filename": name, "mtime": 0.0, "chunk_count": 1,
                           "indexed_at": "2026-09-02", "game_system": "unknown",
                           "game_systems": [], "content_hash": hashlib.sha256(data).hexdigest(),
                           "file_size": len(data)}
    (tmp_path / "index_manifest.json").write_text(json.dumps({"version": 1, "files": entries}))
    return entries


def test_resolve_maps_docs_by_sha256_and_reports_missing(tmp_path):
    files = _manifest(tmp_path, {"MM.pdf": b"monster manual", "PHB.pdf": b"players handbook"})
    lib = {"docs": [
        {"id": "mm", "sha256": hashlib.sha256(b"monster manual").hexdigest(), "title": "MM"},
        {"id": "dmg", "sha256": "0" * 64, "title": "DMG (not indexed)"},
    ], "queries": []}
    corpus, missing = library.resolve(lib, files)
    assert [d.id for d in corpus.documents] == ["mm"]
    assert corpus.documents[0].pdf_path == tmp_path / "MM.pdf"
    assert corpus.documents[0].pdf_sha256 == hashlib.sha256(b"monster manual").hexdigest()
    assert missing == ["dmg"]


def test_select_queries_skips_any_query_whose_doc_is_missing():
    queries = [
        {"id": "L001", "doc": "mm"},
        {"id": "L002", "doc": "dmg"},
        {"id": "L003", "doc": ["mm", "dmg"]},
    ]
    kept, skipped = library.select_queries(queries, present={"mm"})
    assert [q["id"] for q in kept] == ["L001"]
    assert skipped == ["L002", "L003"]


def test_load_library_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "library.yaml"
    p.write_text("docs:\n  - {id: mm, sha256: '%s', title: MM}\n  - {id: mm, sha256: '%s', title: MM2}\nqueries: []\n"
                 % ("a" * 64, "b" * 64))
    with pytest.raises(ValueError, match="duplicate doc id"):
        library.load_library(p)


def test_manifest_files_reads_the_v2_manifest(tmp_path):
    _manifest(tmp_path, {"MM.pdf": b"x"})
    files = library.manifest_files(tmp_path)
    assert list(files.values())[0]["filename"] == "MM.pdf"

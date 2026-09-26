"""Boot-time store setup: a model change marks the whole manifest outdated."""

import server
from legend_lore.library_store import LIBRARY_FILENAME, LibraryStore
from legend_lore.service import (
    IndexManifest,
    ManifestEntry,
    load_manifest,
    save_manifest,
)


def _entry(**kw) -> ManifestEntry:
    return ManifestEntry(
        filename="a.pdf", mtime=0.0, chunk_count=1, indexed_at="t",
        pipeline_version="current", **kw,
    )


def test_open_library_store_marks_manifest_outdated_after_model_change(
    tmp_path, monkeypatch
):
    LibraryStore.open(tmp_path / LIBRARY_FILENAME, "old-model", 4).close()
    manifest = IndexManifest()
    manifest.files["/lib/a.pdf"] = _entry(game_systems=["dnd5e"])
    save_manifest(tmp_path, manifest)

    monkeypatch.setattr(server, "EMBEDDING_MODEL", "new-model")
    monkeypatch.setattr(server, "EMBEDDING_DIM", 4)
    store = server.open_library_store(tmp_path)

    assert store.was_reset
    entry = load_manifest(tmp_path).files["/lib/a.pdf"]
    assert entry.pipeline_version == ""
    assert entry.game_systems == ["dnd5e"]
    store.close()


def test_open_library_store_leaves_manifest_alone_when_model_matches(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(server, "EMBEDDING_MODEL", "m")
    monkeypatch.setattr(server, "EMBEDDING_DIM", 4)
    server.open_library_store(tmp_path).close()
    manifest = IndexManifest()
    manifest.files["/lib/a.pdf"] = _entry()
    save_manifest(tmp_path, manifest)

    store = server.open_library_store(tmp_path)

    assert not store.was_reset
    assert load_manifest(tmp_path).files["/lib/a.pdf"].pipeline_version == "current"
    store.close()

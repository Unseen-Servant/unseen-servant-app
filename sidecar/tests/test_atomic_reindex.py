"""
Tests for atomic re-index — embed failures must not destroy the
previously-indexed chunks, parents, or manifest entry for a source.

The whole point: if Ollama dies mid-sync, the user's last good index is
still searchable until they retry.
"""

import json
from pathlib import Path

import pytest

from legend_lore.service import (
    EmbedBatchError,
    MANIFEST_FILENAME,
    _embed_units,
    _atomic_index_pdf,
    load_manifest,
)
from legend_lore.granularity import EmbedUnit, ParentDoc
from legend_lore.library_store import LibraryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_units(n: int) -> list[EmbedUnit]:
    return [
        EmbedUnit(
            chunk_id=str(i),
            text=f"text {i}",
            parent_id=f"p_{i // 3}",
            chunk_type="prose",
            section_heading=None,
            source_pdf="test.pdf",
            page_start=1,
            page_end=1,
            ordinal=i,
            section_id=None,
            section_path=None,
        )
        for i in range(n)
    ]


def _embed(texts):
    """4-dim stand-in embedder (non-zero, so cosine is defined)."""
    return [[float(i) + 1.0] * 4 for i, _ in enumerate(texts)]


def _boom(message, exc=RuntimeError):
    def embed(texts):
        raise exc(message)
    return embed


@pytest.fixture
def store(tmp_path):
    s = LibraryStore.open(tmp_path / "library.sqlite3", "test", 4)
    yield s
    s.close()


def _unit_ids(store, source: str) -> set[int]:
    """Unit ids currently stored for one book."""
    return {
        uid for (uid,) in store.conn().execute(
            "SELECT u.id FROM units u JOIN documents d ON d.id = u.document_id "
            "WHERE d.path = ?", (source,),
        )
    }


# ---------------------------------------------------------------------------
# Embed-failure -> EmbedBatchError contract
# ---------------------------------------------------------------------------


def test_embed_failure_raises_embed_batch_error():
    """An exception inside the embed function is wrapped with the source path."""
    units = _make_units(6)

    with pytest.raises(EmbedBatchError) as exc_info:
        list(_embed_units(
            _boom("ollama is wedged"), units, Path("/lib/test.pdf"), [],
            batch_size=3, concurrency=2,
        ))
    err = exc_info.value
    assert err.source_path == Path("/lib/test.pdf")
    assert "ollama is wedged" in str(err)
    assert "test.pdf" in str(err)


def test_embed_batch_error_chains_original_cause():
    """The original exception is available via __cause__ for diagnostics."""
    units = _make_units(3)

    with pytest.raises(EmbedBatchError) as exc_info:
        list(_embed_units(
            _boom("bad input", ValueError), units, Path("test.pdf"), [],
            batch_size=3,
        ))
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_embed_batch_retries_transient_reset(monkeypatch):
    """A transient runner reset ("connection reset by peer") is retried and
    recovers, so one dropped connection doesn't abort the file."""
    from legend_lore import service

    monkeypatch.setattr(service.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def flaky_embed(texts):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(
                'Post ".../tokenize": read: connection reset by peer (status code: 400)'
            )
        return _embed(texts)

    out = service._embed_batch(flaky_embed, _make_units(2))
    assert calls["n"] == 2  # failed once, recovered on retry
    assert len(out) == 2


def test_embed_batch_does_not_retry_deterministic_error(monkeypatch):
    """A real error (bad input) fails fast — no retry, no backoff sleep."""
    from legend_lore import service

    monkeypatch.setattr(service.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def boom(texts):
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        service._embed_batch(boom, _make_units(2))
    assert calls["n"] == 1  # not retried


# ---------------------------------------------------------------------------
# Atomic helper: nothing is written until the whole book has embedded
# ---------------------------------------------------------------------------


def test_atomic_index_pdf_writes_nothing_when_embed_fails(store):
    """If embed fails on batch 2 of 3, no chunk of the book reaches the store."""
    pdf_path = Path("/lib/test.pdf")
    units = _make_units(9)  # batch_size=3 -> 3 batches
    parents: list[ParentDoc] = []

    fail_after = {"calls": 0}

    def flaky_embed(texts):
        fail_after["calls"] += 1
        if fail_after["calls"] >= 2:
            raise RuntimeError("network glitch")
        return _embed(texts)

    with pytest.raises(EmbedBatchError):
        list(_atomic_index_pdf(
            pdf_path, "unknown", [], units, parents, store, flaky_embed,
            batch_size=3,
        ))

    assert _unit_ids(store, str(pdf_path)) == set()
    assert store.documents() == []


def test_atomic_index_pdf_preserves_old_chunks_on_failure(store):
    """A re-index that fails leaves the previous chunks for the source intact."""
    pdf_path = Path("/lib/test.pdf")

    # First successful index
    list(_atomic_index_pdf(
        pdf_path, "unknown", [], _make_units(6), [], store, _embed, batch_size=3,
    ))
    v1_ids = _unit_ids(store, str(pdf_path))
    assert len(v1_ids) == 6

    # Second attempt: embed fails on the very first batch of the new attempt
    with pytest.raises(EmbedBatchError):
        list(_atomic_index_pdf(
            pdf_path, "unknown", [], _make_units(6), [], store, _boom("oom"),
            batch_size=3,
        ))

    # Old chunks still there, with their original IDs
    assert _unit_ids(store, str(pdf_path)) == v1_ids


def test_atomic_index_pdf_replaces_book_on_success(store):
    """A successful re-index replaces the old chunks, leaving none of a prior
    larger chunking behind."""
    pdf_path = Path("/lib/test.pdf")

    list(_atomic_index_pdf(
        pdf_path, "unknown", [], _make_units(8), [], store, _embed, batch_size=3,
    ))
    assert len(_unit_ids(store, str(pdf_path))) == 8

    # Re-index with fewer units.
    list(_atomic_index_pdf(
        pdf_path, "unknown", [], _make_units(4), [], store, _embed, batch_size=3,
    ))

    assert len(_unit_ids(store, str(pdf_path))) == 4
    assert store.document_text(str(pdf_path)) == "text 0\ntext 1\ntext 2\ntext 3"
    # The FTS rows swap with the chunks — one row per surviving unit.
    assert len(store.fts("text", k=100)) == 4


# ---------------------------------------------------------------------------
# End-to-end: reindex_file via HTTP, with monkey-patched embed
# ---------------------------------------------------------------------------


def test_reindex_file_failure_preserves_indexed_data(
    client, sample_pdf_path, test_store, tmp_path, monkeypatch
):
    """Embed failure during /api/reindex-file must not destroy old chunks."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    initial_ids = _unit_ids(test_store, str(sample_pdf_path))
    assert initial_ids

    from legend_lore import service
    monkeypatch.setattr(service, "_embed_batch",
        lambda embed_fn, batch: (_ for _ in ()).throw(RuntimeError("ollama down"))
    )

    resp = client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunks"] == 0
    assert data["error"] is not None
    assert "ollama" in data["error"].lower() or "down" in data["error"].lower()

    assert _unit_ids(test_store, str(sample_pdf_path)) == initial_ids


def test_reindex_file_failure_records_last_error(
    client, sample_pdf_path, tmp_path, monkeypatch
):
    """Failure records last_error/last_error_at on the manifest entry."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})

    from legend_lore import service
    monkeypatch.setattr(service, "_embed_batch",
        lambda embed_fn, batch: (_ for _ in ()).throw(RuntimeError("ollama down"))
    )

    client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})

    manifest = load_manifest(tmp_path)
    entry = manifest.files[str(sample_pdf_path)]
    assert entry.last_error is not None
    assert "ollama" in entry.last_error.lower() or "down" in entry.last_error.lower()
    assert entry.last_error_at is not None
    # Previous successful chunk_count is preserved
    assert entry.chunk_count > 0


def test_reindex_file_success_clears_last_error(
    client, sample_pdf_path, tmp_path, monkeypatch
):
    """A successful re-index clears any prior last_error marker."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})

    from legend_lore import service
    monkeypatch.setattr(service, "_embed_batch",
        lambda embed_fn, batch: (_ for _ in ()).throw(RuntimeError("first failure"))
    )
    client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})
    assert load_manifest(tmp_path).files[str(sample_pdf_path)].last_error is not None

    monkeypatch.undo()
    resp = client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})
    assert resp.json()["error"] is None
    entry = load_manifest(tmp_path).files[str(sample_pdf_path)]
    assert entry.last_error is None
    assert entry.last_error_at is None


# ---------------------------------------------------------------------------
# Sync stream: failure mid-Phase-3 preserves old chunks for the failed file
# ---------------------------------------------------------------------------


def _modify_pdf(pdf_path: Path) -> None:
    """Append a byte to the file so its mtime + content hash change.

    Simplest way to make a sync diff classify it as ``to_update`` without
    re-rendering the PDF entirely (which would also change page count).
    """
    with pdf_path.open("ab") as f:
        f.write(b"\n%% modified\n")


def test_sync_stream_phase3_failure_preserves_old_chunks(
    client, sample_pdf_path, large_text_pdf_path, test_store, tmp_path,
    monkeypatch,
):
    """A Phase 3 (update) embed failure preserves the previous chunks.

    Indexes two files, modifies the first, then injects an embed failure
    only when the failing file's batch is processed. The other file should
    re-index successfully and the failed file's old chunks should remain.
    """
    paths = [str(sample_pdf_path), str(large_text_pdf_path)]
    client.post("/api/index-files", json={"paths": paths})
    sample_initial_ids = _unit_ids(test_store, str(sample_pdf_path))
    assert sample_initial_ids

    # Modify both so both end up in to_update; only the sample one will fail.
    _modify_pdf(sample_pdf_path)
    _modify_pdf(large_text_pdf_path)

    from legend_lore import service
    real_embed = service._embed_batch

    def selective_boom(embed_fn, batch):
        # Inspect the text contents — sample PDF is dragonbane themed.
        if any("Fire Drake" in eu.text or "dragon" in eu.text.lower() for eu in batch):
            raise RuntimeError("ollama choked on dragons")
        return real_embed(embed_fn, batch)

    monkeypatch.setattr(service, "_embed_batch", selective_boom)

    resp = client.post("/api/sync-index", json={"selected_paths": paths})
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"], "expected at least one error in the sync result"

    # Sample's old chunks are still there — the failed book was never written
    assert _unit_ids(test_store, str(sample_pdf_path)) == sample_initial_ids

    # large_text_pdf got re-indexed successfully; its manifest entry has no error
    manifest = load_manifest(tmp_path)
    sample_entry = manifest.files[str(sample_pdf_path)]
    large_entry = manifest.files[str(large_text_pdf_path)]
    assert sample_entry.last_error is not None
    assert sample_entry.chunk_count > 0  # previous count preserved
    assert large_entry.last_error is None


def test_sync_stream_phase3_failure_releases_lock(
    client, sample_pdf_path, monkeypatch
):
    """If every file in the sync fails, the sync lock is still released."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    _modify_pdf(sample_pdf_path)

    from legend_lore import service
    monkeypatch.setattr(service, "_embed_batch",
        lambda embed_fn, batch: (_ for _ in ()).throw(RuntimeError("everything fails"))
    )

    # First sync — fails on the embed, but should return 200 with errors,
    # not 500, and must release the lock for the next call.
    resp1 = client.post("/api/sync-index", json={"selected_paths": [str(sample_pdf_path)]})
    assert resp1.status_code == 200
    assert resp1.json()["errors"]

    # Second sync — would 409 if the lock leaked
    resp2 = client.post("/api/sync-index", json={"selected_paths": [str(sample_pdf_path)]})
    assert resp2.status_code == 200

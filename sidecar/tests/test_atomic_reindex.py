"""
Tests for atomic re-index — embed/upsert failures must not destroy the
previously-indexed chunks, parents, or manifest entry for a source.

The whole point: if Ollama dies mid-sync, the user's last good index is
still searchable until they retry.
"""

import json
from pathlib import Path

import pytest

from server import (
    EmbedBatchError,
    MANIFEST_FILENAME,
    _embed_and_upsert_units,
    _atomic_index_pdf,
    chunk_id_prefix,
    load_manifest,
)
from granularity import EmbedUnit, ParentDoc


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
        )
        for i in range(n)
    ]


class _RecordingCollection:
    """Stand-in collection: tracks upserts/deletes and serves get(where=)."""

    def __init__(self):
        self._embedding_function = self._embed
        self.records: dict[str, dict] = {}  # id -> {"source": ..., "doc": ...}

    def _embed(self, texts):
        return [[float(i)] * 4 for i, _ in enumerate(texts)]

    def upsert(self, *, embeddings, documents, metadatas, ids):
        for i, cid in enumerate(ids):
            self.records[cid] = {
                "source": metadatas[i].get("source"),
                "doc": documents[i],
            }

    def delete(self, ids):
        for cid in ids:
            self.records.pop(cid, None)

    def get(self, *, where=None, include=None):
        if where is None:
            return {"ids": list(self.records.keys())}
        source = where.get("source")
        ids = [cid for cid, meta in self.records.items() if meta["source"] == source]
        return {"ids": ids}


# ---------------------------------------------------------------------------
# Embed-failure -> EmbedBatchError contract
# ---------------------------------------------------------------------------


def test_embed_failure_raises_embed_batch_error():
    """An exception inside the embed function is wrapped with the source path."""
    units = _make_units(6)

    class _BoomCollection(_RecordingCollection):
        def _embed(self, texts):
            raise RuntimeError("ollama is wedged")

    coll = _BoomCollection()
    with pytest.raises(EmbedBatchError) as exc_info:
        list(_embed_and_upsert_units(
            coll, units, Path("/lib/test.pdf"), "unknown", "stem",
            batch_size=3, concurrency=2,
        ))
    err = exc_info.value
    assert err.source_path == Path("/lib/test.pdf")
    assert "ollama is wedged" in str(err)
    assert "test.pdf" in str(err)


def test_embed_batch_error_chains_original_cause():
    """The original exception is available via __cause__ for diagnostics."""
    units = _make_units(3)

    class _BoomCollection(_RecordingCollection):
        def _embed(self, texts):
            raise ValueError("bad input")

    coll = _BoomCollection()
    with pytest.raises(EmbedBatchError) as exc_info:
        list(_embed_and_upsert_units(
            coll, units, Path("test.pdf"), "unknown", "stem", batch_size=3,
        ))
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_embed_batch_retries_transient_reset(monkeypatch):
    """A transient runner reset ("connection reset by peer") is retried and
    recovers, so one dropped connection doesn't abort the file."""
    import server

    monkeypatch.setattr(server.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    class _FlakyCollection(_RecordingCollection):
        def _embed(self, texts):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(
                    'Post ".../tokenize": read: connection reset by peer (status code: 400)'
                )
            return [[float(i)] * 4 for i, _ in enumerate(texts)]

    out = server._embed_batch(_FlakyCollection(), _make_units(2))
    assert calls["n"] == 2  # failed once, recovered on retry
    assert len(out) == 2


def test_embed_batch_does_not_retry_deterministic_error(monkeypatch):
    """A real error (bad input) fails fast — no retry, no backoff sleep."""
    import server

    monkeypatch.setattr(server.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    class _BoomCollection(_RecordingCollection):
        def _embed(self, texts):
            calls["n"] += 1
            raise ValueError("bad input")

    with pytest.raises(ValueError):
        server._embed_batch(_BoomCollection(), _make_units(2))
    assert calls["n"] == 1  # not retried


# ---------------------------------------------------------------------------
# Atomic helper: rollback on failure
# ---------------------------------------------------------------------------


def test_atomic_index_pdf_rolls_back_partial_inserts(tmp_path):
    """If embed fails on batch 2 of 3, the first batch's chunks are removed."""
    pdf_path = Path("/lib/test.pdf")
    units = _make_units(9)  # batch_size=3 -> 3 batches
    parents: list[ParentDoc] = []

    coll = _RecordingCollection()
    fail_after = {"calls": 0}
    real_embed = coll._embedding_function

    def flaky_embed(texts):
        fail_after["calls"] += 1
        if fail_after["calls"] >= 2:
            raise RuntimeError("network glitch")
        return real_embed(texts)

    coll._embedding_function = flaky_embed

    with pytest.raises(EmbedBatchError):
        list(_atomic_index_pdf(
            pdf_path, "unknown", units, parents, coll, tmp_path,
            batch_size=3,
        ))

    # No chunks survive for this source — the partial insert was cleaned up
    assert coll.get(where={"source": str(pdf_path)})["ids"] == []


def test_atomic_index_pdf_preserves_old_chunks_on_failure(tmp_path):
    """A re-index that fails leaves the previous chunks for the source intact."""
    pdf_path = Path("/lib/test.pdf")
    coll = _RecordingCollection()

    # First successful index
    units_v1 = _make_units(6)
    list(_atomic_index_pdf(
        pdf_path, "unknown", units_v1, [], coll, tmp_path, batch_size=3,
    ))
    v1_ids = set(coll.get(where={"source": str(pdf_path)})["ids"])
    assert v1_ids
    assert len(v1_ids) == 6

    # Second attempt: embed fails on the very first batch of the new attempt
    coll._embedding_function = lambda texts: (_ for _ in ()).throw(RuntimeError("oom"))
    units_v2 = _make_units(6)

    with pytest.raises(EmbedBatchError):
        list(_atomic_index_pdf(
            pdf_path, "unknown", units_v2, [], coll, tmp_path, batch_size=3,
        ))

    # Old chunks still there, with their original IDs
    after_ids = set(coll.get(where={"source": str(pdf_path)})["ids"])
    assert after_ids == v1_ids


def test_atomic_index_pdf_swaps_in_new_chunks_on_success(tmp_path):
    """A successful re-index replaces old chunks even when content_hash unchanged."""
    pdf_path = Path("/lib/test.pdf")
    coll = _RecordingCollection()

    list(_atomic_index_pdf(
        pdf_path, "unknown", _make_units(8), [], coll, tmp_path, batch_size=3,
    ))
    v1_ids = set(coll.get(where={"source": str(pdf_path)})["ids"])

    # Re-index with fewer units: nonce makes the new prefix distinct, so the
    # cleanup wipes leftover chunks from the prior larger chunking.
    list(_atomic_index_pdf(
        pdf_path, "unknown", _make_units(4), [], coll, tmp_path, batch_size=3,
    ))
    v2_ids = set(coll.get(where={"source": str(pdf_path)})["ids"])

    assert len(v2_ids) == 4
    assert v2_ids.isdisjoint(v1_ids)


# ---------------------------------------------------------------------------
# End-to-end: reindex_file via HTTP, with monkey-patched embed
# ---------------------------------------------------------------------------


def test_reindex_file_failure_preserves_indexed_data(
    client, sample_pdf_path, test_collection, tmp_path, monkeypatch
):
    """Embed failure during /api/reindex-file must not destroy old chunks."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    initial_ids = set(test_collection.get(
        where={"source": str(sample_pdf_path)}, include=[]
    )["ids"])
    assert initial_ids

    import server
    monkeypatch.setattr(
        server, "_embed_batch",
        lambda collection, batch: (_ for _ in ()).throw(RuntimeError("ollama down"))
    )

    resp = client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunks"] == 0
    assert data["error"] is not None
    assert "ollama" in data["error"].lower() or "down" in data["error"].lower()

    after_ids = set(test_collection.get(
        where={"source": str(sample_pdf_path)}, include=[]
    )["ids"])
    assert after_ids == initial_ids


def test_reindex_file_failure_records_last_error(
    client, sample_pdf_path, tmp_path, monkeypatch
):
    """Failure records last_error/last_error_at on the manifest entry."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})

    import server
    monkeypatch.setattr(
        server, "_embed_batch",
        lambda collection, batch: (_ for _ in ()).throw(RuntimeError("ollama down"))
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

    import server
    monkeypatch.setattr(
        server, "_embed_batch",
        lambda collection, batch: (_ for _ in ()).throw(RuntimeError("first failure"))
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
    client, sample_pdf_path, large_text_pdf_path, test_collection, tmp_path,
    monkeypatch,
):
    """A Phase 3 (update) embed failure preserves the previous chunks.

    Indexes two files, modifies the first, then injects an embed failure
    only when the failing file's batch is processed. The other file should
    re-index successfully and the failed file's old chunks should remain.
    """
    paths = [str(sample_pdf_path), str(large_text_pdf_path)]
    client.post("/api/index-files", json={"paths": paths})
    sample_initial_ids = set(test_collection.get(
        where={"source": str(sample_pdf_path)}, include=[]
    )["ids"])
    assert sample_initial_ids

    # Modify both so both end up in to_update; only the sample one will fail.
    _modify_pdf(sample_pdf_path)
    _modify_pdf(large_text_pdf_path)

    import server
    real_embed = server._embed_batch

    def selective_boom(collection, batch):
        # The metadata source is set later in _upsert_batch, so inspect the
        # text contents — sample PDF is dragonbane themed.
        if any("Fire Drake" in eu.text or "dragon" in eu.text.lower() for eu in batch):
            raise RuntimeError("ollama choked on dragons")
        return real_embed(collection, batch)

    monkeypatch.setattr(server, "_embed_batch", selective_boom)

    resp = client.post("/api/sync-index", json={"selected_paths": paths})
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"], "expected at least one error in the sync result"

    # Sample's old chunks are still there — atomic rollback preserved them
    after_ids = set(test_collection.get(
        where={"source": str(sample_pdf_path)}, include=[]
    )["ids"])
    assert after_ids == sample_initial_ids

    # large_text_pdf got re-indexed successfully; its manifest entry has no error
    manifest = load_manifest(tmp_path)
    sample_entry = manifest.files[str(sample_pdf_path)]
    large_entry = manifest.files[str(large_text_pdf_path)]
    assert sample_entry.last_error is not None
    assert sample_entry.chunk_count > 0  # previous count preserved
    assert large_entry.last_error is None


# ---------------------------------------------------------------------------
# Ollama embed timeout — defends against wedged Ollama hanging the sync
# ---------------------------------------------------------------------------


def test_build_ollama_embedding_function_default_timeout(monkeypatch):
    """Default timeout is 120s — long enough for a slow embed batch but
    short enough that a wedged Ollama can't hang sync forever."""
    from server import build_ollama_embedding_function

    monkeypatch.delenv("OLLAMA_EMBED_TIMEOUT_SECONDS", raising=False)
    ef = build_ollama_embedding_function()
    assert ef.timeout == 120


def test_build_ollama_embedding_function_env_override(monkeypatch):
    """OLLAMA_EMBED_TIMEOUT_SECONDS overrides the default."""
    from server import build_ollama_embedding_function

    monkeypatch.setenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "30")
    ef = build_ollama_embedding_function()
    assert ef.timeout == 30


def test_sync_stream_phase3_failure_releases_lock(
    client, sample_pdf_path, monkeypatch
):
    """If every file in the sync fails, the sync lock is still released."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    _modify_pdf(sample_pdf_path)

    import server
    monkeypatch.setattr(
        server, "_embed_batch",
        lambda collection, batch: (_ for _ in ()).throw(RuntimeError("everything fails"))
    )

    # First sync — fails on the embed, but should return 200 with errors,
    # not 500, and must release the lock for the next call.
    resp1 = client.post("/api/sync-index", json={"selected_paths": [str(sample_pdf_path)]})
    assert resp1.status_code == 200
    assert resp1.json()["errors"]

    # Second sync — would 409 if the lock leaked
    resp2 = client.post("/api/sync-index", json={"selected_paths": [str(sample_pdf_path)]})
    assert resp2.status_code == 200

"""Stage G — the one-SQLite-file index commit (plan §3.2 G, §3.3). Tested with
fake vectors (no embedder/model needed): schema, one-txn commit, idempotent
re-index, content-hash change detection, vector round-trip, FTS."""
import dataclasses

import numpy as np

from domain.models import Chunk, ChunkKind, Document, Section, Unit
from index.store import DIM, Store


def _doc():
    sections = (Section(id="d:s0", title="Monsters", level=1, parent_id=None, page_start=0, page_end=1),)
    chunks = (
        Chunk(id="d:c0", doc_id="d", section_id="d:s0", ordinal=0, kind=ChunkKind.prose,
              text="a goblin has armor class 15", page_start=0, page_end=0, lang="en"),
        Chunk(id="d:c1", doc_id="d", section_id="d:s0", ordinal=1, kind=ChunkKind.table,
              text="club 1d4", page_start=1, page_end=1, lang="en"),
    )
    units = (
        Unit(id="d:c0:u0", chunk_id="d:c0", text="a goblin has armor class 15",
             kind=ChunkKind.prose, page_start=0, page_end=0, lang="en"),
        Unit(id="d:c1:u0", chunk_id="d:c1", text="club 1d4",
             kind=ChunkKind.table, page_start=1, page_end=1, lang="en"),
    )
    return Document(id="d", path="/x.pdf", title="X", page_count=2,
                    sections=sections, chunks=chunks, units=units)


def _vecs(n):
    rng = np.random.default_rng(0)
    v = rng.standard_normal((n, DIM)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_commit_persists_counts(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1")
    assert s.counts("d") == {"sections": 1, "chunks": 2, "units": 2}


def test_recommit_replaces_not_duplicates(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1")
    s.commit(_doc(), _vecs(2), content_hash="h2")
    assert s.counts("d") == {"sections": 1, "chunks": 2, "units": 2}


def test_change_detection(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1")
    assert s.is_unchanged("d", "h1") is True
    assert s.is_unchanged("d", "h2") is False
    assert s.is_unchanged("missing", "h1") is False


def test_vector_round_trips_f32(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    v = _vecs(2)
    s.commit(_doc(), v, content_hash="h1")
    assert np.array_equal(s.get_vector("d:c0:u0"), v[0])


def test_fts_finds_unit_by_word(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1")
    ids = s.search_fts("goblin")
    assert "d:c0:u0" in ids and "d:c1:u0" not in ids


def test_document_row_records_pipeline_version(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1", pipeline_version=7)
    assert s.pipeline_version("d") == 7


def test_document_row_round_trips_toc_and_page_labels(tmp_path):
    # Provenance the plan schema requires (§3.3): toc + printed page labels are
    # extracted then were dropped at commit; Phase-3 result payloads need labels.
    s = Store.open(str(tmp_path / "idx.db"))
    doc = dataclasses.replace(_doc(),
                              toc=((1, "Monsters", 3), (2, "Goblins", 4)),
                              page_labels=("i", "ii", "1", "2"))
    s.commit(doc, _vecs(2), content_hash="h1")
    assert s.get_toc("d") == ((1, "Monsters", 3), (2, "Goblins", 4))
    assert s.get_page_labels("d") == ("i", "ii", "1", "2")


def test_toc_and_page_labels_default_empty(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1")  # _doc() carries neither
    assert s.get_toc("d") == () and s.get_page_labels("d") == ()


def test_vocab_deltas_accumulate(tmp_path):
    # Persisted, incremental per-document deltas (§3.3, Stage G line 115). This is
    # the schema + write API; population (which terms) is the Phase-3 spell rung.
    s = Store.open(str(tmp_path / "idx.db"))
    s.add_vocab([("goblin", "en", 3), ("armor", "en", 1)])
    s.add_vocab([("goblin", "en", 2)])  # a second document's delta
    assert s.vocab_freq("goblin", "en") == 5
    assert s.vocab_freq("armor", "en") == 1
    assert s.vocab_freq("missing", "en") == 0

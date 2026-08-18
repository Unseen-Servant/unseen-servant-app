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


def test_commit_indexes_fts_texts_when_given(tmp_path):
    # heading-prepended FTS: the lexical index gets the same breadcrumb-prefixed
    # text the dense side embeds, so BM25 can match on section headings too.
    s = Store.open(str(tmp_path / "idx.db"))
    fts = ["Combat > Weapons\nunit 0 body", "Combat\nunit 1 body", "Combat\nunit 2 body"]
    s.commit(_doc3(), _basis_vecs(), content_hash="h1", fts_texts=fts)
    assert "d:c1:u0" in s.search_fts("combat")   # heading term now searchable
    assert s.search_fts("weapons") == ["d:c0:u0"]  # term only in the prepended heading


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


def _doc3():
    """A doc with 3 units in one section — for dense-search ranking tests."""
    sections = (Section(id="d:s0", title="Combat", level=1, parent_id=None, page_start=0, page_end=2),)
    chunks = tuple(
        Chunk(id=f"d:c{i}", doc_id="d", section_id="d:s0", ordinal=i, kind=ChunkKind.prose,
              text=f"chunk {i}", page_start=i, page_end=i, lang="en")
        for i in range(3)
    )
    units = tuple(
        Unit(id=f"d:c{i}:u0", chunk_id=f"d:c{i}", text=f"unit {i} body",
             kind=ChunkKind.prose, page_start=i, page_end=i, lang="en")
        for i in range(3)
    )
    return Document(id="d", path="/lib/monster_manual.pdf", title="Monster Manual",
                    page_count=3, sections=sections, chunks=chunks, units=units)


def _basis_vecs():
    """3 near-orthogonal L2-normalized vectors so nearest-neighbour is unambiguous."""
    v = np.zeros((3, DIM), np.float32)
    for i in range(3):
        v[i, i * 100] = 1.0
    return v


def test_search_dense_ranks_nearest_unit_first(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    v = _basis_vecs()
    s.commit(_doc3(), v, content_hash="h1")
    hits = s.search_dense(v[1], k=3)                 # query == unit 1's vector
    assert [uid for uid, _ in hits][0] == "d:c1:u0"  # nearest ranks first
    assert len(hits) == 3 and hits[0][1] > hits[1][1]  # scores descending


def test_search_dense_respects_k(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc3(), _basis_vecs(), content_hash="h1")
    assert len(s.search_dense(_basis_vecs()[0], k=2)) == 2


def test_hydrate_joins_unit_to_section_and_document(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc3(), _basis_vecs(), content_hash="h1")
    row = s.hydrate(["d:c1:u0"])["d:c1:u0"]
    assert row["text"] == "unit 1 body"
    assert row["section_heading"] == "Combat"
    assert row["filename"] == "monster_manual.pdf" and row["source"] == "Monster Manual"
    assert row["page_start"] == 1 and row["page_end"] == 1


def test_hydrate_returns_parent_chunk_and_ids_for_dedupe(tmp_path):
    # rung 4 needs the parent chunk text + chunk_id/section_id to dedupe and assemble.
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc3(), _basis_vecs(), content_hash="h1")
    row = s.hydrate(["d:c1:u0"])["d:c1:u0"]
    assert row["chunk_id"] == "d:c1" and row["section_id"] == "d:s0"
    assert row["chunk_text"] == "chunk 1"  # the parent's fuller text


def test_vocab_deltas_accumulate(tmp_path):
    # Persisted, incremental per-document deltas (§3.3, Stage G line 115). This is
    # the schema + write API; population (which terms) is the Phase-3 spell rung.
    s = Store.open(str(tmp_path / "idx.db"))
    s.add_vocab([("goblin", "en", 3), ("armor", "en", 1)])
    s.add_vocab([("goblin", "en", 2)])  # a second document's delta
    assert s.vocab_freq("goblin", "en") == 5
    assert s.vocab_freq("armor", "en") == 1
    assert s.vocab_freq("missing", "en") == 0


def test_build_vocab_from_indexed_units(tmp_path):
    # rung 7 backfill: library vocab (term frequencies) from the indexed unit text,
    # no re-index. Idempotent — a second call rebuilds, doesn't double.
    s = Store.open(str(tmp_path / "idx.db"))
    s.commit(_doc(), _vecs(2), content_hash="h1")  # "a goblin has armor class 15" / "club 1d4"
    s.build_vocab()
    s.build_vocab()  # idempotent
    assert s.vocab_freq("goblin", "en") == 1 and s.vocab_freq("armor", "en") == 1
    d = s.vocab_dict()
    assert d["goblin"] == 1 and "club" in d and d.get("missing", 0) == 0

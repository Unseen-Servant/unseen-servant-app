"""Unit tests for library_store — the single-file library store."""

import sqlite3

import numpy as np
import pytest

from legend_lore.granularity import EmbedUnit, ParentDoc
from legend_lore.library_store import LibraryStore
from tests.conftest import document_text

DIM = 4
MODEL = "test-model"


@pytest.fixture
def store(tmp_path):
    s = LibraryStore.open(tmp_path / "library.sqlite3", MODEL, DIM)
    yield s
    s.close()


def _unit(source: str, ordinal: int, text: str, parent: str = "p0",
          heading: str | None = "Monsters", page: int = 1) -> EmbedUnit:
    return EmbedUnit(
        chunk_id=f"c{ordinal}", text=text, parent_id=parent,
        chunk_type="prose", section_heading=heading, source_pdf=source,
        page_start=page, page_end=page, ordinal=ordinal,
        section_id="s-" + parent, section_path=heading,
    )


def _parent(source: str, pid: str = "p0", text: str = "parent text") -> ParentDoc:
    return ParentDoc(
        parent_id=pid, text=text, section_heading="Monsters",
        chunk_type="prose", source_pdf=source, page_start=1, page_end=1,
        section_id="s-" + pid, section_path="Monsters",
    )


def _index(store, path, texts, vectors, game_system="unknown", systems=(),
           page_labels=None):
    # Real parent ids hash the path, so they're unique per book.
    pid = f"{path}#p0"
    units = [_unit(path, i, t, parent=pid) for i, t in enumerate(texts)]
    return store.replace_document(
        path, game_system, systems, units,
        embed_texts=[f"Monsters\n\n{t}" for t in texts],
        vectors=vectors, parents=[_parent(path, pid)], page_labels=page_labels,
    )


def _axis(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def _rows(store, table: str) -> int:
    return store._conn().execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# -- open / meta --------------------------------------------------------------

def test_reopen_with_same_model_keeps_content(tmp_path):
    path = tmp_path / "library.sqlite3"
    s = LibraryStore.open(path, MODEL, DIM)
    _index(s, "/lib/a.pdf", ["dragon"], [_axis(0)])
    s.close()

    s = LibraryStore.open(path, MODEL, DIM)
    assert not s.was_reset
    assert s.count_units() == 1
    s.close()


@pytest.mark.parametrize("model, dim", [("other-model", DIM), (MODEL, 8)])
def test_reopen_with_other_model_clears_store(tmp_path, model, dim):
    path = tmp_path / "library.sqlite3"
    s = LibraryStore.open(path, MODEL, DIM)
    _index(s, "/lib/a.pdf", ["dragon"], [_axis(0)])
    s.close()

    s = LibraryStore.open(path, model, dim)
    assert s.was_reset
    assert s.count_units() == 0 and s.documents() == []
    # The vector table was rebuilt for the new dimension.
    units = [_unit("/lib/a.pdf", 0, "dragon")]
    s.replace_document("/lib/a.pdf", "unknown", (), units, ["dragon"],
                       [[1.0] + [0.0] * (dim - 1)], [])
    assert len(s.knn([1.0] + [0.0] * (dim - 1), k=5)) == 1
    s.close()


def test_new_file_uses_incremental_auto_vacuum(store):
    assert store._conn().execute("PRAGMA auto_vacuum").fetchone()[0] == 2


# -- replace_document ---------------------------------------------------------

def test_replace_document_indexes_units_vectors_fts_and_parents(store):
    _index(store, "/lib/Monster Manual.pdf", ["fire drake", "ice troll"],
           [_axis(0), _axis(1)], game_system="dnd5e", page_labels={1: "iv"})

    (hit_id, dist), = store.knn(_axis(1), k=1)
    assert dist == pytest.approx(0.0, abs=1e-6)
    unit = store.hydrate([hit_id])[hit_id]
    assert unit.text == "ice troll"
    assert unit.metadata == {
        "source": "/lib/Monster Manual.pdf",
        "filename": "Monster Manual.pdf",
        "chunk": 1,
        "game_system": "dnd5e",
        "chunk_type": "prose",
        "section_heading": "Monsters",
        "page_start": 1,
        "page_end": 1,
        "page_label_start": "iv",
        "page_label_end": "iv",
        "parent_id": "/lib/Monster Manual.pdf#p0",
        "section_id": "s-/lib/Monster Manual.pdf#p0",
        "section_path": "Monsters",
    }
    assert store.fts("troll", k=5) == [hit_id]
    assert _rows(store, "parents") == 1


def test_reindex_replaces_every_row_of_the_book(store):
    _index(store, "/lib/a.pdf", ["one", "two", "three"],
           [_axis(0), _axis(1), _axis(2)])
    _index(store, "/lib/a.pdf", ["only"], [_axis(3)])

    assert document_text(store, "/lib/a.pdf") == "only"
    for table in ("units", "unit_vec", "unit_fts", "parents", "documents"):
        assert _rows(store, table) == 1, table
    assert store.fts("three", k=5) == []


def test_failed_reindex_leaves_previous_index_intact(store):
    _index(store, "/lib/a.pdf", ["dragon"], [_axis(0)])

    with pytest.raises(ValueError):
        _index(store, "/lib/a.pdf", ["new"], [[1.0] * (DIM + 1)])
    # A failure inside the transaction (duplicate ordinal) rolls back too.
    units = [_unit("/lib/a.pdf", 0, "x"), _unit("/lib/a.pdf", 0, "y")]
    with pytest.raises(sqlite3.IntegrityError):
        store.replace_document("/lib/a.pdf", "unknown", (), units,
                               ["x", "y"], [_axis(0), _axis(1)], [])

    assert document_text(store, "/lib/a.pdf") == "dragon"
    assert len(store.knn(_axis(0), k=5)) == 1


def test_replace_document_rejects_length_mismatch(store):
    with pytest.raises(ValueError):
        _index(store, "/lib/a.pdf", ["a", "b"], [_axis(0)])


# -- rename -------------------------------------------------------------------

def test_rename_document_moves_the_book_and_keeps_ids(store):
    _index(store, "/lib/old.pdf", ["dragon"], [_axis(0)])
    (uid, _), = store.knn(_axis(0), k=1)

    assert store.rename_document("/lib/old.pdf", "/lib/sub/new.pdf")
    unit = store.hydrate([uid])[uid]
    assert (unit.source, unit.filename) == ("/lib/sub/new.pdf", "new.pdf")
    assert unit.section_id == "s-/lib/old.pdf#p0"
    assert not store.rename_document("/lib/missing.pdf", "/lib/x.pdf")


def test_rename_folder_rewrites_only_the_prefix(store):
    _index(store, "/lib/b/one.pdf", ["a"], [_axis(0)])
    _index(store, "/lib/b/deep/two.pdf", ["b"], [_axis(1)])
    _index(store, "/lib/bc/three.pdf", ["c"], [_axis(2)])

    assert store.rename_folder("/lib/b/", "/lib/renamed/") == 2
    assert [d.path for d in store.documents()] == [
        "/lib/bc/three.pdf", "/lib/renamed/deep/two.pdf", "/lib/renamed/one.pdf",
    ]


# -- tags and scope -----------------------------------------------------------

def test_scope_by_systems_matches_primary_secondary_and_unknown(store):
    a = _index(store, "/lib/a.pdf", ["a"], [_axis(0)], "dnd5e")
    b = _index(store, "/lib/b.pdf", ["b"], [_axis(1)], "osr", ["osr", "dnd5e"])
    c = _index(store, "/lib/c.pdf", ["c"], [_axis(2)])

    assert store.scope_document_ids() is None
    assert sorted(store.scope_document_ids(systems=["dnd5e"])) == [a, b]
    assert store.scope_document_ids(systems=["unknown"]) == [c]
    assert store.scope_document_ids(systems=["pf2e"]) == []
    assert store.scope_document_ids(filename="b.pdf") == [b]
    assert store.scope_document_ids(paths=["/lib/a.pdf", "/lib/c.pdf"],
                                    systems=["dnd5e"]) == [a]
    assert store.scope_document_ids(paths=[]) == []


def test_set_systems_retags_the_book(store):
    doc = _index(store, "/lib/a.pdf", ["a"], [_axis(0)], "dnd5e")

    assert store.set_systems("/lib/a.pdf", "osr", ["osr", "cairn"])
    assert store.scope_document_ids(systems=["dnd5e"]) == []
    assert store.scope_document_ids(systems=["cairn"]) == [doc]
    (stats,) = store.documents()
    assert (stats.game_system, stats.systems) == ("osr", ("cairn", "osr"))
    assert not store.set_systems("/lib/missing.pdf", "osr", [])


def test_knn_and_fts_respect_scope_and_merge_to_k(store):
    # Two books, three units each; a scope over both must return k rows
    # total, nearest first, not k per book.
    a = _index(store, "/lib/a.pdf", ["goblin a0", "goblin a1", "goblin a2"],
               [_axis(0), [0.9, 0.1, 0, 0], [0.5, 0.5, 0, 0]])
    b = _index(store, "/lib/b.pdf", ["goblin b0", "goblin b1", "goblin b2"],
               [[0.95, 0.05, 0, 0], _axis(2), _axis(3)])

    hits = store.knn(_axis(0), k=3, doc_ids=[a, b])
    assert len(hits) == 3
    assert [d for _, d in hits] == sorted(d for _, d in hits)
    texts = [store.hydrate([u])[u].text for u, _ in hits]
    assert texts == ["goblin a0", "goblin b0", "goblin a1"]

    only_b = store.knn(_axis(0), k=3, doc_ids=[b])
    assert {store.hydrate([u])[u].source for u, _ in only_b} == {"/lib/b.pdf"}
    assert store.knn(_axis(0), k=3, doc_ids=[]) == []

    assert len(store.fts("goblin", k=10)) == 6
    assert len(store.fts("goblin", k=10, doc_ids=[a])) == 3
    assert store.fts("goblin", k=10, doc_ids=[]) == []


# -- delete / clear -----------------------------------------------------------

def test_delete_document_removes_every_row_and_reclaims_space(store):
    rng = np.random.default_rng(0)
    big = [f"unit {i}" for i in range(2000)]
    _index(store, "/lib/big.pdf", big, rng.standard_normal((2000, DIM)))
    _index(store, "/lib/keep.pdf", ["keep"], [_axis(0)])
    conn = store._conn()
    pages_before = conn.execute("PRAGMA page_count").fetchone()[0]

    assert store.delete_document("/lib/big.pdf") == 2000

    assert [d.path for d in store.documents()] == ["/lib/keep.pdf"]
    for table in ("units", "unit_vec", "unit_fts", "parents"):
        assert _rows(store, table) == 1, table
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    assert conn.execute("PRAGMA page_count").fetchone()[0] < pages_before
    assert store.delete_document("/lib/big.pdf") == 0


def test_clear_empties_the_library(store):
    _index(store, "/lib/a.pdf", ["a"], [_axis(0)], "dnd5e")
    store.clear()

    for table in ("units", "unit_vec", "unit_fts", "parents", "documents",
                  "document_systems"):
        assert _rows(store, table) == 0, table
    _index(store, "/lib/a.pdf", ["a"], [_axis(0)])
    assert store.count_units() == 1


# -- reads for listings and spelling ------------------------------------------

def test_documents_lists_books_with_unit_counts(store):
    _index(store, "/lib/a.pdf", ["x", "y"], [_axis(0), _axis(1)], "dnd5e")
    _index(store, "/lib/b.pdf", ["z"], [_axis(2)])

    stats = store.documents()
    assert [(d.filename, d.game_system, d.systems, d.units, d.pages)
            for d in stats] == [
        ("a.pdf", "dnd5e", ("dnd5e",), 2, 1),
        ("b.pdf", "unknown", (), 1, 1),
    ]
    assert store.count_units() == 3


def test_fts_texts_and_phrase_counts_read_the_embed_text(store):
    _index(store, "/lib/a.pdf", ["thief skill", "this skill", "thief skill"],
           [_axis(0), _axis(1), _axis(2)])

    assert sorted(store.fts_texts())[0] == "Monsters\n\nthief skill"
    assert store.count_phrases([("thief", "skill"), ("this", "skill")]) == {
        ("thief", "skill"): 2, ("this", "skill"): 1,
    }


def test_each_thread_gets_its_own_connection(store):
    import threading

    _index(store, "/lib/a.pdf", ["dragon"], [_axis(0)])
    seen = []
    t = threading.Thread(target=lambda: seen.append(
        (store._conn(), len(store.knn(_axis(0), k=1)))))
    t.start()
    t.join()
    assert seen[0][0] is not store._conn() and seen[0][1] == 1

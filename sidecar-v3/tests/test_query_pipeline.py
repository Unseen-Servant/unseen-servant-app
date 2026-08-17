"""Phase 3 rung 1 — dense-only retrieval orchestration (plan §3.4, §4 ladder).
Thin composition over the tested store primitives (search_dense + hydrate),
with a fake embed_fn so no model is needed. query/ returns plain dicts — it
owns no engine types (the evals adapter maps to SearchResult)."""
import numpy as np

from domain.models import Chunk, ChunkKind, Document, Section, Unit
from index.store import DIM, Store
from query.pipeline import dense_search, search


def _doc():
    sections = (Section(id="d:s0", title="Combat", level=1, parent_id=None, page_start=0, page_end=2),)
    chunks = tuple(Chunk(id=f"d:c{i}", doc_id="d", section_id="d:s0", ordinal=i, kind=ChunkKind.prose,
                         text=f"chunk {i}", page_start=i, page_end=i, lang="en") for i in range(3))
    units = tuple(Unit(id=f"d:c{i}:u0", chunk_id=f"d:c{i}", text=f"unit {i} body",
                       kind=ChunkKind.prose, page_start=i, page_end=i, lang="en") for i in range(3))
    return Document(id="d", path="/lib/phb.pdf", title="PHB", page_count=3,
                    sections=sections, chunks=chunks, units=units)


def _doc_2sec():
    # two sections, one unit each — for the "distinct sections survive" case
    sections = (Section(id="d:s0", title="A", level=1, parent_id=None, page_start=0, page_end=0),
                Section(id="d:s1", title="B", level=1, parent_id=None, page_start=1, page_end=1))
    chunks = (Chunk(id="d:c0", doc_id="d", section_id="d:s0", ordinal=0, kind=ChunkKind.prose,
                    text="chunk zero", page_start=0, page_end=0, lang="en"),
              Chunk(id="d:c1", doc_id="d", section_id="d:s1", ordinal=1, kind=ChunkKind.prose,
                    text="chunk one", page_start=1, page_end=1, lang="en"))
    units = (Unit(id="d:c0:u0", chunk_id="d:c0", text="unit zero", kind=ChunkKind.prose,
                  page_start=0, page_end=0, lang="en"),
             Unit(id="d:c1:u0", chunk_id="d:c1", text="unit one", kind=ChunkKind.prose,
                  page_start=1, page_end=1, lang="en"))
    return Document(id="d", path="/lib/phb.pdf", title="PHB", page_count=2,
                    sections=sections, chunks=chunks, units=units)


def _basis():
    v = np.zeros((3, DIM), np.float32)
    for i in range(3):
        v[i, i * 100] = 1.0
    return v


def test_dense_search_returns_ranked_hydrated_results(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    v = _basis()
    s.commit(_doc(), v, content_hash="h1")
    embed_fn = lambda texts: np.array([v[2]], np.float32)  # query embeds to unit 2's vector
    res = dense_search(s, embed_fn, "anything", k=3)
    assert res[0]["unit_id"] == "d:c2:u0" and res[0]["rank"] == 0
    assert res[0]["section_heading"] == "Combat" and res[0]["filename"] == "phb.pdf"
    assert res[0]["relevance"] > res[1]["relevance"]


def test_dense_search_respects_k(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    v = _basis()
    s.commit(_doc(), v, content_hash="h1")
    assert len(dense_search(s, lambda t: np.array([v[0]], np.float32), "q", k=2)) == 2


# -- rung 4: parents & dedupe (query-time) --

def test_search_dedupes_by_section_and_returns_parent_text(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    v = _basis()
    s.commit(_doc(), v, content_hash="h1")  # 3 units, all in section d:s0
    res = search(s, lambda t: np.array([v[1]], np.float32), "q", k=5)
    assert len(res) == 1                      # one section → one result, not three
    assert res[0]["section_id"] == "d:s0"
    assert res[0]["text"] == "chunk 1"        # parent chunk text (best-scoring unit c1)
    assert res[0]["matched_text"] == "unit 1 body"


def test_search_keeps_distinct_sections(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    vv = np.zeros((2, DIM), np.float32); vv[0, 0] = 1.0; vv[1, 100] = 1.0
    s.commit(_doc_2sec(), vv, content_hash="h1")
    res = search(s, lambda t: np.array([vv[0]], np.float32), "q", k=5)
    assert {r["section_id"] for r in res} == {"d:s0", "d:s1"}  # both distinct sections kept


def test_search_respects_k_after_dedupe(tmp_path):
    s = Store.open(str(tmp_path / "idx.db"))
    vv = np.zeros((2, DIM), np.float32); vv[0, 0] = 1.0; vv[1, 100] = 1.0
    s.commit(_doc_2sec(), vv, content_hash="h1")
    assert len(search(s, lambda t: np.array([vv[0]], np.float32), "q", k=1)) == 1

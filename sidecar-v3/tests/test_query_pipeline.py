"""Phase 3 rung 1 — dense-only retrieval orchestration (plan §3.4, §4 ladder).
Thin composition over the tested store primitives (search_dense + hydrate),
with a fake embed_fn so no model is needed. query/ returns plain dicts — it
owns no engine types (the evals adapter maps to SearchResult)."""
import numpy as np

from domain.models import Chunk, ChunkKind, Document, Section, Unit
from index.store import DIM, Store
from query.pipeline import dense_search


def _doc():
    sections = (Section(id="d:s0", title="Combat", level=1, parent_id=None, page_start=0, page_end=2),)
    chunks = tuple(Chunk(id=f"d:c{i}", doc_id="d", section_id="d:s0", ordinal=i, kind=ChunkKind.prose,
                         text=f"chunk {i}", page_start=i, page_end=i, lang="en") for i in range(3))
    units = tuple(Unit(id=f"d:c{i}:u0", chunk_id=f"d:c{i}", text=f"unit {i} body",
                       kind=ChunkKind.prose, page_start=i, page_end=i, lang="en") for i in range(3))
    return Document(id="d", path="/lib/phb.pdf", title="PHB", page_count=3,
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

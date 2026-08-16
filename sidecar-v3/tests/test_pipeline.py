"""End-to-end ingestion orchestrator (plan §3.2) — wires extract→layout→
structure→chunk→linearize→embed→store. The two model stages (layout, embed) are
injected as callables, so the wiring is tested with fakes (no ONNX assets);
production passes the real PP-DocLayout session + bge-m3 Embedder."""
import fitz
import numpy as np
import pytest

from domain.models import Block, BlockKind, FontStats
from index.embedder import DIM
from index.store import Store
from ingest.pipeline import IndexReport, index_document


@pytest.fixture
def pdf(tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 90), "The Goblin", fontsize=18, fontname="hebo")
    p.insert_text((72, 140), "A goblin has armor class 15.", fontsize=11, fontname="helv")
    path = tmp_path / "m.pdf"
    doc.save(path)
    return str(path)


def fake_layout(raw):
    """Each span → a Block (bold ⇒ heading, else prose) — enough to exercise the
    structure/chunk/linearize wiring without the ONNX model."""
    blocks, ro = [], 0
    for pe in raw.pages:
        for i, s in enumerate(pe.spans):
            kind = BlockKind.heading if s.bold else BlockKind.prose
            blocks.append(Block(id=f"{raw.doc_id}:p{pe.page}:b{i}", kind=kind, text=s.text, page=pe.page,
                                bbox=s.bbox, reading_order=ro, font_stats=FontStats(size=s.size, bold=s.bold)))
            ro += 1
    return tuple(blocks)


def fake_embed(texts):
    rng = np.random.default_rng(0)
    v = rng.standard_normal((len(texts), DIM)).astype(np.float32)
    return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)


def test_index_document_end_to_end(pdf, tmp_path):
    store = Store.open(str(tmp_path / "idx.db"))
    rep = index_document(pdf, store, fake_layout, fake_embed, doc_id="m")
    assert isinstance(rep, IndexReport) and rep.skipped is False
    assert rep.units >= 1 and rep.sections >= 1
    assert store.counts("m")["units"] == rep.units
    assert store.search_fts("goblin")  # a unit made it into FTS


def test_reindex_skips_unchanged(pdf, tmp_path):
    store = Store.open(str(tmp_path / "idx.db"))
    index_document(pdf, store, fake_layout, fake_embed, doc_id="m")
    rep2 = index_document(pdf, store, fake_layout, fake_embed, doc_id="m")
    assert rep2.skipped is True
    assert store.counts("m")["units"] >= 1  # still indexed


def test_every_unit_has_a_vector(pdf, tmp_path):
    store = Store.open(str(tmp_path / "idx.db"))
    index_document(pdf, store, fake_layout, fake_embed, doc_id="m")
    uid = store.search_fts("goblin")[0]
    assert store.get_vector(uid).shape == (DIM,)


def test_doc_id_defaults_to_filename_stem(pdf, tmp_path):
    store = Store.open(str(tmp_path / "idx.db"))
    rep = index_document(pdf, store, fake_layout, fake_embed)
    assert rep.doc_id == "m"

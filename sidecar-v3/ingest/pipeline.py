"""End-to-end ingestion orchestrator (plan §3.2 A→G).

`index_document(pdf, store, layout_fn, embed_fn)` threads the seven stages:
extract → layout → structure → chunk → linearize → embed → store.commit, in one
document transaction, with SHA-256 content-hash change detection (skip unchanged).

The two model-dependent stages are injected as callables so the wiring is unit-
testable with fakes:
  layout_fn(raw)  -> tuple[Block]     (prod: `make_layout_fn(session)`)
  embed_fn(texts) -> np.ndarray (N,DIM)  (prod: `Embedder(...).embed`)
No import from sidecar/.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from domain.models import Block, Document, SCHEMA_VERSION
from index.embedder import DIM
from ingest.chunk import chunk_blocks
from ingest.extract import RawExtraction, extract
from ingest.layout import LABELS_M, layout
from ingest.linearize import to_units
from ingest.structure import build_sections


@dataclass(frozen=True, slots=True)
class IndexReport:
    doc_id: str
    sections: int
    chunks: int
    units: int
    skipped: bool = False


def build_embed_inputs(units, chunks, sections) -> list[str]:
    """Rung 2 (heading-prepend, plan §4 ladder): the EMBEDDED text is the section
    breadcrumb (root→leaf titles) + the unit body, so short units (table rows,
    one-line rules) carry their section context into the vector. Stored unit text
    is unchanged. Output order follows `units` (vectors are row-aligned at commit)."""
    section_by_id = {s.id: s for s in sections}
    chunk_section = {c.id: c.section_id for c in chunks}

    def crumb(section_id) -> str:
        titles, sid = [], section_id
        while sid is not None and (s := section_by_id.get(sid)) is not None:
            titles.append(s.title.strip())
            sid = s.parent_id
        return " > ".join(reversed(titles))

    return [f"{c}\n{u.text}" if (c := crumb(chunk_section.get(u.chunk_id))) else u.text
            for u in units]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def index_document(
    pdf_path: str,
    store,
    layout_fn: Callable[[RawExtraction], Sequence[Block]],
    embed_fn: Callable[[list[str]], np.ndarray],
    *,
    doc_id: str | None = None,
    pipeline_version: int = SCHEMA_VERSION,
) -> IndexReport:
    raw = extract(pdf_path, doc_id)
    content_hash = _sha256(pdf_path)
    if store.is_unchanged(raw.doc_id, content_hash):
        return IndexReport(raw.doc_id, 0, 0, 0, skipped=True)

    blocks = tuple(layout_fn(raw))
    sections, assign = build_sections(blocks, raw.toc, raw.doc_id)
    chunks = chunk_blocks(blocks, assign, raw.doc_id)
    units = tuple(u for c in chunks for u in to_units(c))
    embed_inputs = build_embed_inputs(units, chunks, sections)  # breadcrumb + unit text
    vectors = embed_fn(embed_inputs) if units else np.zeros((0, DIM), np.float32)

    doc = Document(
        id=raw.doc_id, path=raw.path, title=raw.title, page_count=raw.page_count,
        needs_ocr=raw.needs_ocr, toc=raw.toc, page_labels=raw.page_labels,
        sections=sections, blocks=blocks, chunks=chunks, units=units,
    )
    store.commit(doc, vectors, content_hash, pipeline_version, fts_texts=embed_inputs)
    return IndexReport(raw.doc_id, len(sections), len(chunks), len(units), skipped=False)


def make_layout_fn(session, labels: list[str] = LABELS_M):
    """Production layout callable from a loaded PP-DocLayout ONNX session."""
    return lambda raw: layout(raw, session, labels)

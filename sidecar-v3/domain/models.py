"""sidecar-v3 domain IR — the typed intermediate representation.

Markdown is never the IR (constitution #6): ingestion PRODUCES these typed
models and every text rendering is a derived view. Each retrieval-bearing
model carries bbox + page + section, so highlight-and-scroll, region
rendering, and a printed-page-label drill-in are possible downstream
(plan §3.2, §3.4). Nothing here imports from sidecar/ (v2) — the two
packages are isolated (constitution #7).

Data only, no behaviour: populated by ingest/ and index/, consumed by
query/. This is the "real home" a Phase-1 spike lands its winner into.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

SCHEMA_VERSION = 1  # bump when a persisted field changes; index/store.py migrates.


class BlockKind(str, Enum):
    """A layout region's type, from the ONNX layout pass (plan §3.2 B)."""

    heading = "heading"
    prose = "prose"
    table = "table"
    caption = "caption"
    image = "image"
    artifact = "artifact"  # running header/footer/furniture — dropped with confidence (fixes R2/R4)


class ChunkKind(str, Enum):
    prose = "prose"
    table = "table"


@dataclass(frozen=True, slots=True)
class BBox:
    """A region on a page, in PDF points."""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True, slots=True)
class BBoxSpan:
    """A bbox tied to the page it sits on. Chunks and units carry a *list* of
    these because one unit can straddle a page break — the cross_page case the
    eval harness measures and v2 gets wrong."""

    page: int  # 0-based physical page index
    bbox: BBox


@dataclass(frozen=True, slots=True)
class FontStats:
    """Per-block font aggregate — a heading-promotion signal for structure.py
    (plan §3.2 C/D, E; now italic-aware)."""

    size: float
    bold: bool = False
    italic: bool = False
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Block:
    """An ordered native PDF text block annotated by layout classification.
    Every block keeps page, native bbox, and font_stats."""

    id: str
    kind: BlockKind
    text: str
    page: int
    bbox: BBox
    reading_order: int  # column-aware XY-cut order within the document (fixes R1)
    font_stats: FontStats | None = None
    lang: str | None = None  # per-block language ID; the library is mixed FR/EN


@dataclass(frozen=True, slots=True)
class Section:
    """A node in the heading tree (plan §3.2 E), persisted with its page span.
    Parents in retrieval are section nodes (the 6000-char cap is applied at
    assembly, not stored here)."""

    id: str
    title: str
    level: int
    parent_id: str | None
    page_start: int
    page_end: int


@dataclass(frozen=True, slots=True)
class Unit:
    """A small embed unit — what actually gets a vector (plan §3.2 F): a
    ~400-char prose split or one linearized table row. Belongs to a Chunk."""

    id: str
    chunk_id: str
    text: str
    kind: ChunkKind
    page_start: int
    page_end: int
    bbox_spans: tuple[BBoxSpan, ...] = ()
    lang: str | None = None


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrieval chunk (plan §3.3 schema): structure-aware boundary, ~1000-char
    soft cap, no overlap. Mirrors one `chunks` SQLite row."""

    id: str
    doc_id: str
    section_id: str | None
    ordinal: int
    kind: ChunkKind
    text: str
    page_start: int
    page_end: int
    bbox_spans: tuple[BBoxSpan, ...] = ()
    lang: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """The product of ingestion (plan §3.2): a typed tree, not Markdown. Holds
    its own structure; text renderings are derived from it."""

    id: str  # corpus id, e.g. "srd_5_1"
    path: str
    title: str
    page_count: int
    needs_ocr: bool = False  # any page lacked a text layer (opt-in slow OCR pass)
    lang: str | None = None
    toc: tuple[tuple[int, str, int], ...] = ()  # (level, title, 1-based page) — provenance/nav
    page_labels: tuple[str, ...] = ()  # printed page label per physical page (result citations)
    sections: tuple[Section, ...] = ()
    blocks: tuple[Block, ...] = ()
    chunks: tuple[Chunk, ...] = ()
    units: tuple[Unit, ...] = ()

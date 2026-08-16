"""F. Structure-aware chunking (plan §3.2 F).

Group typed Blocks into Chunks with the validated v2 boundaries: headings and
tables are walls, prose accumulates to a ~1000-char soft cap with NO overlap,
and tables are atomic (never split, never merged — the atomic-tables prior).
Furniture (`artifact`) and `image` blocks are skipped. Every Chunk carries its
section_id (from Stage E), page span, and bbox spans. No import from sidecar/.
"""
from __future__ import annotations

from typing import Sequence

from domain.models import BBox, BBoxSpan, Block, BlockKind, Chunk, ChunkKind

SOFT_CAP = 1000  # chars; prose flushes once a block pushes the buffer past this
_TEXT = {BlockKind.prose, BlockKind.caption}


def _make(doc_id: str, ordinal: int, kind: ChunkKind, blocks: list[Block], section_id) -> Chunk:
    pages = [b.page for b in blocks]
    return Chunk(
        id=f"{doc_id}:c{ordinal}",
        doc_id=doc_id,
        section_id=section_id,
        ordinal=ordinal,
        kind=kind,
        text="\n\n".join(b.text for b in blocks),
        page_start=min(pages),
        page_end=max(pages),
        bbox_spans=tuple(BBoxSpan(page=b.page, bbox=b.bbox) for b in blocks),
        lang=None,
    )


def chunk_blocks(
    blocks: Sequence[Block], assign: dict[str, str | None], doc_id: str
) -> tuple[Chunk, ...]:
    """Blocks (any order) + block→section map → structure-aware Chunks."""
    ordered = sorted(blocks, key=lambda b: b.reading_order)
    chunks: list[Chunk] = []
    buf: list[Block] = []

    def flush() -> None:
        if buf:
            chunks.append(_make(doc_id, len(chunks), ChunkKind.prose, buf, assign.get(buf[0].id)))
            buf.clear()

    for b in ordered:
        if b.kind is BlockKind.heading:
            flush()  # wall — the heading text lives in the Section title, not a chunk
        elif b.kind is BlockKind.table:
            flush()
            chunks.append(_make(doc_id, len(chunks), ChunkKind.table, [b], assign.get(b.id)))
        elif b.kind in _TEXT:
            buf.append(b)
            if sum(len(x.text) for x in buf) >= SOFT_CAP:
                flush()
        # artifact / image: skipped, no flush (furniture never breaks prose flow)
    flush()
    return tuple(chunks)

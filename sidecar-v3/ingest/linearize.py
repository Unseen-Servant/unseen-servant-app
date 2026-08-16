"""F (embed units). Small units — what actually gets a vector (plan §3.2 F).

Prose chunks split into ~400-char units at word boundaries (no overlap, no
mid-word). Table chunks emit one unit per row (the small-unit + dedupe-by-parent
prior). Every unit inherits its chunk's section/page/bbox/lang.

Deferred to the Phase-3 table-units ablation rung: the "Header: cell; …"
row reformat with the coverage-ratio guard + title-row heuristic (the +0.152 MRR
v2 win). It needs per-cell structure preserved from Stage B (the row-major
linearize currently space-joins cells); do that when the rung is built, so this
stays a clean per-row baseline for the ablation to beat.
"""
from __future__ import annotations

from domain.models import Chunk, ChunkKind, Unit

UNIT_CAP = 400  # chars per prose unit


def _split_prose(text: str, cap: int) -> list[str]:
    parts: list[str] = []
    cur = ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > cap:
            parts.append(cur)
            cur = w
        else:
            cur = w if not cur else f"{cur} {w}"
    if cur:
        parts.append(cur)
    return parts or [""]


def to_units(chunk: Chunk) -> tuple[Unit, ...]:
    if chunk.kind is ChunkKind.table:
        texts = [r.strip() for r in chunk.text.split("\n") if r.strip()]
    else:
        texts = _split_prose(chunk.text, UNIT_CAP)
    return tuple(
        Unit(
            id=f"{chunk.id}:u{i}",
            chunk_id=chunk.id,
            text=t,
            kind=chunk.kind,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            bbox_spans=chunk.bbox_spans,
            lang=chunk.lang,
        )
        for i, t in enumerate(texts)
    )

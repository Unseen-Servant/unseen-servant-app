"""Parent-document retrieval: small embed units, parent generation context.

Validated by chunk_granularity_spike (sibling experiments repo, verdict
2026-04-27). The recipe:

  structure_aware chunks
    → group consecutive chunks by section_heading breadcrumb (parents)
        - new parent on breadcrumb change
        - new parent on cap > PARENT_HARD_CAP chars
    → sub-split prose chunks into ~SMALL_TARGET-char paragraph-aware
      embed units; tables linearize into one row-as-sentence unit per
      row (atomic fallback when unparseable or coverage < COVERAGE_MIN)
    → embed_units carry parent_id; parents indexed for fetch at retrieval

Why contiguous-run grouping (not group-by-breadcrumb-globally): on
Black-Flag, every monster card emits ``## **ACTIONS**`` as its own
heading at the same Markdown level as the monster name, which collapses
all monster ACTIONS sections into a single 225k-char parent under naive
grouping. Contiguous-run keeps each card's ACTIONS local to its parent.

Why the 6,000-char parent cap: even with contiguous-run grouping, a
runaway breadcrumb can produce a multi-section parent. The cap bounds
generation context per result.

Tables linearized: each pipe-table row embeds as its own
"<header>: <cell>; ..." sentence, all pointing at the parent that
contains the full table — so retrieval matches individual rows while
the reader still gets the whole table in context (table_retrieval_spike,
+0.152 MRR@5). Unparseable or lossy parses (coverage_ratio below
COVERAGE_MIN) fall back to the pre-#327 atomic embed unit.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from chunker import Chunk
from linearize import coverage_ratio, linearize_table

logger = logging.getLogger(__name__)


SMALL_TARGET = 400
SMALL_HARD = 600
SMALL_FLOOR = 200
PARENT_HARD_CAP = 6000
COVERAGE_MIN = 0.6

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


@dataclass(frozen=True)
class EmbedUnit:
    """A single thing the embedder will see."""
    chunk_id: str
    text: str
    parent_id: str
    chunk_type: str
    section_heading: str | None
    source_pdf: str
    page_start: int
    page_end: int
    ordinal: int


@dataclass(frozen=True)
class ParentDoc:
    """A unit of generation context. What the consumer sees at retrieval."""
    parent_id: str
    text: str
    section_heading: str | None
    chunk_type: str
    source_pdf: str
    page_start: int
    page_end: int


def _split_prose(text: str, target: int = SMALL_TARGET) -> list[str]:
    """Split prose into ~target-char fragments, paragraph-aware.

    Algorithm: split on \\n\\n, accumulate paragraphs into a buffer,
    flush when buffer >= target. If a single paragraph alone exceeds
    SMALL_HARD, split on sentence boundaries; failing that, hard-split
    on words.
    """
    text = text.strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(p) > SMALL_HARD:
            if buf:
                out.append(buf)
                buf = ""
            sentences = _SENT_SPLIT_RE.split(p)
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if len(s) > SMALL_HARD:
                    words = s.split()
                    chunk_buf = ""
                    for w in words:
                        candidate = (chunk_buf + " " + w).strip() if chunk_buf else w
                        if len(candidate) > SMALL_HARD and chunk_buf:
                            out.append(chunk_buf)
                            chunk_buf = w
                        else:
                            chunk_buf = candidate
                    if chunk_buf:
                        s = chunk_buf
                candidate = (buf + " " + s).strip() if buf else s
                if len(candidate) >= target and buf:
                    out.append(buf)
                    buf = s
                else:
                    buf = candidate
            continue
        candidate = (buf + "\n\n" + p).strip() if buf else p
        if len(candidate) >= target and buf and len(buf) >= SMALL_FLOOR:
            out.append(buf)
            buf = p
        else:
            buf = candidate
    if buf.strip():
        out.append(buf)
    return out


def _make_parent_id(source_pdf: str, group_idx: int, label_text: str | None) -> str:
    """Stable, collision-free parent_id.

    Group-ordinal is what disambiguates the same breadcrumb appearing in
    different parts of the doc. Hash of (source, idx, label) keeps the
    id short and SQLite-PK friendly.
    """
    safe_label = (label_text or "orphan").replace("\n", " ")[:60]
    digest = hashlib.sha256(
        f"{source_pdf}::{group_idx}::{safe_label}".encode()
    ).hexdigest()[:16]
    return f"p_{digest}"


def _group_into_parents(chunks: list[Chunk]) -> list[list[Chunk]]:
    """Walk chunks in document order. Start a new parent every time the
    breadcrumb changes OR the running text size would exceed
    PARENT_HARD_CAP. Same-breadcrumb-but-non-adjacent chunks become
    distinct parents."""
    groups: list[list[Chunk]] = []
    current: list[Chunk] = []
    current_size = 0
    prev_bc: str | None | object = object()
    for c in chunks:
        bc = c.section_heading
        next_size = current_size + len(c.text) + 2
        if (bc != prev_bc) or (current and next_size > PARENT_HARD_CAP):
            if current:
                groups.append(current)
            current = [c]
            current_size = len(c.text)
        else:
            current.append(c)
            current_size = next_size
        prev_bc = bc
    if current:
        groups.append(current)
    return groups


def build(chunks: list[Chunk]) -> tuple[list[EmbedUnit], list[ParentDoc]]:
    """Group chunks into parents; sub-split prose into embed units.

    Tables are linearized into row-sentence embed units pointing at
    their parent; unparseable/lossy tables fall back to a single
    atomic unit. Returns (embed_units, parents) — both keyed/linked
    via parent_id.
    """
    groups = _group_into_parents(chunks)

    parents: list[ParentDoc] = []
    chunk_to_pid: dict[int, str] = {}

    for gi, group in enumerate(groups):
        pid = _make_parent_id(group[0].source_pdf, gi, group[0].section_heading)
        text = "\n\n".join(c.text for c in group).strip()
        types = {c.chunk_type for c in group}
        ptype = next(iter(types)) if len(types) == 1 else "mixed"
        parents.append(ParentDoc(
            parent_id=pid,
            text=text,
            section_heading=group[0].section_heading,
            chunk_type=ptype,
            source_pdf=group[0].source_pdf,
            page_start=min(c.page_start for c in group),
            page_end=max(c.page_end for c in group),
        ))
        for c in group:
            chunk_to_pid[c.ordinal] = pid

    embed_units: list[EmbedUnit] = []
    embed_ordinal = 0
    n_tables = n_linearized = n_row_units = n_fallback = 0
    for c in chunks:
        pid = chunk_to_pid[c.ordinal]
        if c.chunk_type == "table":
            n_tables += 1
            header, sentences = linearize_table(c.text)
            if sentences and coverage_ratio(c.text, header, sentences) >= COVERAGE_MIN:
                n_linearized += 1
                n_row_units += len(sentences)
                for sent in sentences:
                    embed_units.append(EmbedUnit(
                        chunk_id=f"{embed_ordinal}",
                        text=sent,
                        parent_id=pid,
                        chunk_type="table",
                        section_heading=c.section_heading,
                        source_pdf=c.source_pdf,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        ordinal=embed_ordinal,
                    ))
                    embed_ordinal += 1
            else:
                n_fallback += 1
                embed_units.append(EmbedUnit(
                    chunk_id=f"{embed_ordinal}",
                    text=c.text,
                    parent_id=pid,
                    chunk_type="table",
                    section_heading=c.section_heading,
                    source_pdf=c.source_pdf,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    ordinal=embed_ordinal,
                ))
                embed_ordinal += 1
            continue
        for sub in _split_prose(c.text):
            embed_units.append(EmbedUnit(
                chunk_id=f"{embed_ordinal}",
                text=sub,
                parent_id=pid,
                chunk_type=c.chunk_type,
                section_heading=c.section_heading,
                source_pdf=c.source_pdf,
                page_start=c.page_start,
                page_end=c.page_end,
                ordinal=embed_ordinal,
            ))
            embed_ordinal += 1

    if n_tables:
        logger.info(
            "%s: linearized %d/%d tables into %d row units (%d atomic fallbacks)",
            chunks[0].source_pdf, n_linearized, n_tables, n_row_units, n_fallback,
        )

    return embed_units, parents

"""Structure-aware Markdown chunker.

Breaks at Markdown heading and pipe-table boundaries; keeps tables atomic;
falls back to paragraph-aware splitting within a heading section. Maintains
a heading stack so each chunk carries a section_heading breadcrumb.

Validated against the prior fixed-window baseline in the chunker spike
(MRR@5 0.626 vs 0.573 at the 1000-char soft cap):
https://github.com/Unseen-Servant/unseen-legend-lore-experiments/blob/main/chunker_spike/FINDINGS.md
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from .embedder import EMBEDDING_MODEL
from .heading_text import strip_markup


CHUNKER_VERSION = "structure_aware-v3"
PIPELINE_VERSION = f"{CHUNKER_VERSION}/{EMBEDDING_MODEL}"
SOFT_CAP = 1000
HARD_CAP = 20000

ChunkType = Literal["prose", "table", "heading", "list", "mixed"]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_PAGE_MARKER_RE = re.compile(r"^<!--\s*page\s+(\d+)\s*-->\s*$")


@dataclass(frozen=True)
class PageMarkdown:
    page_number: int
    markdown: str


@dataclass(frozen=True)
class Chunk:
    text: str
    page_start: int
    page_end: int
    chunk_type: ChunkType
    section_heading: str | None
    source_pdf: str
    chunker: str
    ordinal: int
    section_id: str | None = None
    section_path: str | None = None


def _breadcrumb(stack: list[tuple[int, str, str]]) -> str | None:
    if not stack:
        return None
    return " > ".join(text for _, text, _ in stack)


def _section_id(source_pdf: str, ordinal: int, path_titles: list[str]) -> str:
    digest = hashlib.sha256(f"{source_pdf}::{ordinal}::{' > '.join(path_titles)}".encode()).hexdigest()[:16]
    return f"s_{digest}"


def _section_path(stack: list[tuple[int, str, str]]) -> str | None:
    return "/".join(sid for _, _, sid in stack) if stack else None


def _paragraphs(lines: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """Group buffered (line, page) pairs into paragraphs split on blank
    lines; each paragraph carries the first and last page it touches."""
    out: list[tuple[str, int, int]] = []
    buf: list[str] = []
    ps = pe = None
    for line, page in lines:
        if not line.strip():
            if buf:
                out.append(("\n".join(buf).strip(), ps, pe))
                buf, ps, pe = [], None, None
            continue
        buf.append(line)
        ps = page if ps is None else ps
        pe = page
    if buf:
        out.append(("\n".join(buf).strip(), ps, pe))
    return [p for p in out if p[0]]


def _emit_prose(
    paragraphs: list[tuple[str, int, int]],
    heading: str | None,
    section_id: str | None,
    section_path: str | None,
    source_pdf: str,
    start_ordinal: int,
    soft_cap: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = start_ordinal
    buf, bps, bpe = "", None, None

    def flush():
        nonlocal buf, bps, bpe, ordinal
        if buf.strip():
            chunks.append(Chunk(text=buf, page_start=bps, page_end=bpe, chunk_type="prose",
                                section_heading=heading, section_id=section_id,
                                section_path=section_path, source_pdf=source_pdf,
                                chunker=CHUNKER_VERSION, ordinal=ordinal))
            ordinal += 1
        buf, bps, bpe = "", None, None

    for para, ps, pe in paragraphs:
        candidate = (buf + "\n\n" + para).strip() if buf else para
        if len(candidate) <= soft_cap:
            buf, bps, bpe = candidate, (ps if bps is None else bps), pe
            continue
        flush()
        buf, bps, bpe = para, ps, pe
    flush()
    return chunks


def _enforce_hard_cap(chunks: list[Chunk], hard_cap: int) -> list[Chunk]:
    """Split any chunk over hard_cap on \\n\\n boundaries; renumber ordinals.

    Defensive guard for the embedder's context limit (bge-m3 native = 8192 tokens).
    Not exercised on the spike's corpus but a future PDF could hit it via an
    oversized atomic table or a single mega-paragraph.
    """
    out: list[Chunk] = []
    ordinal = 0
    for c in chunks:
        if len(c.text) <= hard_cap:
            out.append(Chunk(**{**c.__dict__, "ordinal": ordinal}))
            ordinal += 1
            continue
        remaining = c.text
        while len(remaining) > hard_cap:
            cut = remaining.rfind("\n\n", 0, hard_cap)
            if cut <= 0:
                # Tables join rows with single \n and never contain \n\n —
                # prefer a row boundary over a mid-row character cut.
                cut = remaining.rfind("\n", 0, hard_cap)
            if cut <= 0:
                cut = hard_cap
            piece, remaining = remaining[:cut].strip(), remaining[cut:].strip()
            if piece:
                out.append(Chunk(**{**c.__dict__, "text": piece, "ordinal": ordinal}))
                ordinal += 1
        if remaining:
            out.append(Chunk(**{**c.__dict__, "text": remaining, "ordinal": ordinal}))
            ordinal += 1
    return out


def structure_aware(
    pages: list[PageMarkdown],
    source_pdf: str,
    soft_cap: int = SOFT_CAP,
    hard_cap: int = HARD_CAP,
) -> list[Chunk]:
    """Walk Markdown pages, emit chunks at heading and table boundaries."""
    chunks: list[Chunk] = []
    ordinal = 0
    section_counter = 0
    heading_stack: list[tuple[int, str, str]] = []
    buffer_lines: list[tuple[str, int]] = []
    current_page = 0

    def flush_prose():
        nonlocal ordinal, buffer_lines
        if not buffer_lines:
            return
        emitted = _emit_prose(
            _paragraphs(buffer_lines),
            _breadcrumb(heading_stack),
            heading_stack[-1][2] if heading_stack else None,
            _section_path(heading_stack),
            source_pdf,
            ordinal,
            soft_cap,
        )
        chunks.extend(emitted)
        ordinal += len(emitted)
        buffer_lines = []

    for page in pages:
        current_page = page.page_number
        lines = page.markdown.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]

            if _PAGE_MARKER_RE.match(line):
                i += 1
                continue

            hm = _HEADING_RE.match(line)
            if hm:
                level = len(hm.group(1))
                text = strip_markup(hm.group(2))
                flush_prose()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                if text:
                    section_counter += 1
                    sid = _section_id(
                        source_pdf,
                        section_counter,
                        [t for _, t, _ in heading_stack] + [text],
                    )
                    heading_stack.append((level, text, sid))
                i += 1
                continue

            if _TABLE_ROW_RE.match(line):
                flush_prose()
                table_lines = [line]
                table_page_start = current_page
                j = i + 1
                while j < len(lines) and _TABLE_ROW_RE.match(lines[j]):
                    table_lines.append(lines[j])
                    j += 1
                chunks.append(Chunk(
                    text="\n".join(table_lines).strip(),
                    page_start=table_page_start,
                    page_end=current_page,
                    chunk_type="table",
                    section_heading=_breadcrumb(heading_stack),
                    source_pdf=source_pdf,
                    chunker=CHUNKER_VERSION,
                    ordinal=ordinal,
                    section_id=heading_stack[-1][2] if heading_stack else None,
                    section_path=_section_path(heading_stack),
                ))
                ordinal += 1
                i = j
                continue

            buffer_lines.append((line, current_page))
            i += 1

    flush_prose()
    return _enforce_hard_cap(chunks, hard_cap)

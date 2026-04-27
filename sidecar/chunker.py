"""Structure-aware Markdown chunker.

Breaks at Markdown heading and pipe-table boundaries; keeps tables atomic;
falls back to paragraph-aware splitting within a heading section. Maintains
a heading stack so each chunk carries a section_heading breadcrumb.

Validated against the prior fixed-window baseline in the chunker spike
(MRR@5 0.626 vs 0.573 at the 1000-char soft cap):
https://github.com/Unseen-Servant/unseen-legend-lore-experiments/blob/main/chunker_spike/FINDINGS.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


CHUNKER_VERSION = "structure_aware-v2"
EMBEDDING_MODEL = "bge-m3"
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


def _breadcrumb(stack: list[tuple[int, str]]) -> str | None:
    if not stack:
        return None
    return " > ".join(text for _, text in stack)


def _emit_prose(
    body_lines: list[str],
    page_start: int,
    page_end: int,
    heading: str | None,
    source_pdf: str,
    start_ordinal: int,
    soft_cap: int,
) -> list[Chunk]:
    text = "\n".join(body_lines).strip()
    if not text:
        return []
    chunks: list[Chunk] = []
    ordinal = start_ordinal
    buf = ""
    for para in re.split(r"\n\s*\n", text):
        candidate = (buf + "\n\n" + para).strip() if buf else para
        if len(candidate) <= soft_cap:
            buf = candidate
            continue
        if buf:
            chunks.append(Chunk(
                text=buf,
                page_start=page_start,
                page_end=page_end,
                chunk_type="prose",
                section_heading=heading,
                source_pdf=source_pdf,
                chunker=CHUNKER_VERSION,
                ordinal=ordinal,
            ))
            ordinal += 1
        buf = para
    if buf.strip():
        chunks.append(Chunk(
            text=buf,
            page_start=page_start,
            page_end=page_end,
            chunk_type="prose",
            section_heading=heading,
            source_pdf=source_pdf,
            chunker=CHUNKER_VERSION,
            ordinal=ordinal,
        ))
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
    heading_stack: list[tuple[int, str]] = []
    buffer_lines: list[str] = []
    buffer_page_start: int | None = None
    buffer_page_end: int | None = None
    current_page = 0

    def flush_prose():
        nonlocal ordinal, buffer_lines, buffer_page_start, buffer_page_end
        if not buffer_lines or buffer_page_start is None:
            buffer_lines = []
            buffer_page_start = None
            buffer_page_end = None
            return
        emitted = _emit_prose(
            buffer_lines,
            buffer_page_start,
            buffer_page_end or buffer_page_start,
            _breadcrumb(heading_stack),
            source_pdf,
            ordinal,
            soft_cap,
        )
        chunks.extend(emitted)
        ordinal += len(emitted)
        buffer_lines = []
        buffer_page_start = None
        buffer_page_end = None

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
                text = hm.group(2).strip()
                flush_prose()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, text))
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
                ))
                ordinal += 1
                i = j
                continue

            if buffer_page_start is None:
                buffer_page_start = current_page
            buffer_page_end = current_page
            buffer_lines.append(line)
            i += 1

    flush_prose()
    return _enforce_hard_cap(chunks, hard_cap)

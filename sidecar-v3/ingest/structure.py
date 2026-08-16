"""E. Section tree (plan §3.2 E).

Headings come from three agreeing signals — the layout model's `heading` blocks,
font-size clustering (level = size rank), and TOC-depth pinning (a heading whose
title matches a TOC entry takes that depth) — with junk-heading rejection
(sentence-shaped or stat-line blocks are demoted to content, the R2 fix). Output:
a real `Section` tree (parent_id + page span) and a block→section assignment for
Stage F. Pure over the typed Blocks; no model, no import from sidecar/.
"""
from __future__ import annotations

import re
from typing import Sequence

from domain.models import Block, BlockKind, Section

_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _is_junk_heading(text: str) -> bool:
    """Reject shapes that are not real headings (fixes the R2 junk-breadcrumb
    problem): sentence-length text, no letters, or stat-line shapes (≥2 numbers,
    e.g. 'AC 15 HP 7 Speed 30'). 'Chapter 3' / 'Level 1 Spells' keep 1 number."""
    t = text.strip()
    if len(t) > 80:
        return True
    if not any(c.isalpha() for c in t):
        return True
    if len(_NUM.findall(t)) >= 2:
        return True
    return False


def build_sections(
    blocks: Sequence[Block], toc: Sequence[tuple[int, str, int]], doc_id: str
) -> tuple[tuple[Section, ...], dict[str, str | None]]:
    """Return (sections, block_id → section_id). Content before the first heading
    maps to None; heading blocks map to their own section."""
    def is_heading(b: Block) -> bool:
        return b.kind is BlockKind.heading and b.font_stats is not None and not _is_junk_heading(b.text)

    headings = [b for b in blocks if is_heading(b)]
    sizes = sorted({h.font_stats.size for h in headings}, reverse=True)
    size_level = {sz: i + 1 for i, sz in enumerate(sizes)}
    toc_level = {_norm(title): lvl for lvl, title, _ in toc}
    hset = {h.id for h in headings}

    def level_of(h: Block) -> int:
        return toc_level.get(_norm(h.text), size_level[h.font_stats.size])

    ordered = sorted(blocks, key=lambda b: b.reading_order)
    nodes: list[dict] = []          # mutable section records
    assign: dict[str, str | None] = {}
    stack: list[tuple[int, int]] = []  # (level, node index) of open sections
    n = 0
    for b in ordered:
        if b.id in hset:
            lvl = level_of(b)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            parent = nodes[stack[-1][1]]["id"] if stack else None
            sid = f"{doc_id}:s{n}"
            n += 1
            idx = len(nodes)
            nodes.append({"id": sid, "title": b.text.strip(), "level": lvl, "parent_id": parent,
                          "page_start": b.page, "page_end": b.page, "children": []})
            if stack:
                nodes[stack[-1][1]]["children"].append(idx)
            stack.append((lvl, idx))
            assign[b.id] = sid
        else:
            if stack:
                cur = nodes[stack[-1][1]]
                assign[b.id] = cur["id"]
                cur["page_end"] = max(cur["page_end"], b.page)
            else:
                assign[b.id] = None

    # Parents span their descendants (bottom-up; children were appended after parents).
    for i in range(len(nodes) - 1, -1, -1):
        for ci in nodes[i]["children"]:
            nodes[i]["page_start"] = min(nodes[i]["page_start"], nodes[ci]["page_start"])
            nodes[i]["page_end"] = max(nodes[i]["page_end"], nodes[ci]["page_end"])

    sections = tuple(
        Section(id=s["id"], title=s["title"], level=s["level"], parent_id=s["parent_id"],
                page_start=s["page_start"], page_end=s["page_end"])
        for s in nodes
    )
    return sections, assign

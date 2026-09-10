"""Heading-hierarchy promotion — flat ``##`` → ``#`` / ``##`` / ``###``.

Ported verbatim from heading_hierarchy_spike (Unseen-Servant/unseen-legend-lore-experiments).
The spike validated three strategies; production uses ``toc_then_font``:

  1. ``font_cluster`` — assign a level to each ``##`` heading by clustering
     its (rounded font-size, bold) signature. Top cluster (most frequent) →
     ``##``, larger clusters → ``#``, smaller clusters → ``###``. Per-PDF —
     no cross-corpus state.

  2. ``toc`` — derive level from ``Document.get_toc(simple=True)`` entry
     depth via case-insensitive token-overlap matching on the same page.

  3. ``toc_then_font`` — recommended production composition: TOC entries at
     depth 1 (chapters/parts) take precedence; everything else falls
     through to font_cluster. Depth ≥ 2 TOC entries are intentionally
     ignored — TOC nesting frequently mismatches the chunker's linear
     heading-stack ancestry (e.g. BFRPG's "Cloud Dragon Age Table" at
     depth 2 would otherwise spuriously parent every later monster).

API:

    promote_markdown(
        pages: list[dict],          # [{"page_number": int, "markdown": str}, ...]
        spans_pages: list[dict],    # [{"page_number": int, "spans": [...]}, ...]
        toc: dict,                  # {"entries": [[level, title, page1], ...]}
        strategy: str = "font_cluster",
    ) -> tuple[list[dict], dict]    # (rewritten pages, promotion report)

Heading text recovery — pymupdf4llm corrupts some SRD heading text
(truncated bold, character-reordering bugs). Token-overlap matching
(lowercase tokens, length ≥ 2) tolerates both: any token-overlap with a
page span counts as a match. The (size, bold) representative is taken
from the LARGEST-font matching span. Unmatched headings fall back to
their original level — conservative, never destructive.
"""
from __future__ import annotations

import re
from collections import Counter

from heading_text import sanitize

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TOKEN_SPLIT_RE = re.compile(r"\W+", re.UNICODE)


def _tokenize(s: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT_RE.split(s.lower()) if len(t) >= 2}


def _strip_md_emphasis(s: str) -> str:
    s = s.strip()
    while s and s[0] == "*":
        s = s[1:]
    while s and s[-1] == "*":
        s = s[:-1]
    return s.strip()


def _heading_font_signature(
    md_text: str,
    page_spans: list[dict],
) -> tuple[float, bool] | None:
    """Best-effort (rounded_size, bold) for a Markdown heading line.

    Returns None when no token overlaps any span on the page (truncated
    ``**`` or character-reorder corruption with no recoverable token).
    """
    cleaned = _strip_md_emphasis(md_text)
    md_tokens = _tokenize(cleaned)
    if not md_tokens:
        return None
    matched: list[dict] = []
    for sp in page_spans:
        sp_text = sp.get("text", "")
        sp_tokens = _tokenize(sp_text)
        if md_tokens & sp_tokens:
            matched.append(sp)
    if not matched:
        return None
    rep = max(matched, key=lambda sp: sp["size"])
    return (round(float(rep["size"]), 1), bool(rep["bold"]))


def _md_heading_lines(md: str) -> list[tuple[int, int, str]]:
    """Return [(line_index, level, text), ...] for each Markdown heading.

    Splits on ``\\n`` only (not ``splitlines()``) so bare ``\\r`` characters
    inside CR-fragmented prose stay embedded in their containing line. R1
    downstream depends on those ``\\r``s; treating them as separators here
    would silently break the SRD's CR-rejoin pass.
    """
    out: list[tuple[int, int, str]] = []
    for i, line in enumerate(md.split("\n")):
        m = HEADING_RE.match(line)
        if not m:
            continue
        out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def collect_heading_signatures(
    pages: list[dict],
    spans_pages: list[dict],
) -> list[dict]:
    spans_by_page = {p["page_number"]: p["spans"] for p in spans_pages}
    rows: list[dict] = []
    for page in pages:
        page_num = page["page_number"]
        page_spans = spans_by_page.get(page_num, [])
        for line_idx, level, text in _md_heading_lines(page["markdown"]):
            parts = sanitize(text, page_spans)
            if not parts:
                rows.append({"page_number": page_num, "line_idx": line_idx,
                             "original_level": level, "text": "", "parts": [], "sig": None})
                continue
            first_text, first_sig = parts[0]
            sig = first_sig or _heading_font_signature(first_text, page_spans)
            rows.append({
                "page_number": page_num,
                "line_idx": line_idx,
                "original_level": level,
                "text": first_text,
                "parts": parts,
                "sig": sig,
            })
    return rows


def build_font_cluster_levels(rows: list[dict]) -> dict:
    """Map each (size, bold) signature → promoted level.

    Modal cluster stays at level 2; larger clusters get level 1 (top
    cluster) or level 2 (the rest); smaller clusters get level 3.
    """
    hist = Counter(r["sig"] for r in rows if r["sig"] is not None)
    if not hist:
        return {"modal_sig": None, "level_by_sig": {}, "histogram": []}

    modal_sig, _modal_count = hist.most_common(1)[0]
    modal_size, modal_bold = modal_sig

    sorted_sigs_desc = sorted(hist.keys(), key=lambda s: (-s[0], not s[1]))

    level_by_sig: dict[tuple[float, bool], int] = {}
    larger_than_modal = [s for s in sorted_sigs_desc if s[0] > modal_size or (s[0] == modal_size and s[1] and not modal_bold)]
    smaller_than_modal = [s for s in sorted_sigs_desc if s[0] < modal_size or (s[0] == modal_size and not s[1] and modal_bold)]

    larger_count = len(larger_than_modal)
    if larger_count >= 2:
        level_by_sig[larger_than_modal[0]] = 1
        for s in larger_than_modal[1:]:
            level_by_sig[s] = 2
    elif larger_count == 1:
        level_by_sig[larger_than_modal[0]] = 1

    level_by_sig[modal_sig] = 2

    for s in smaller_than_modal:
        level_by_sig[s] = 3

    histogram = [
        {"size": s[0], "bold": s[1], "count": c, "promoted_level": level_by_sig.get(s)}
        for s, c in hist.most_common()
    ]
    return {
        "modal_sig": modal_sig,
        "level_by_sig": level_by_sig,
        "histogram": histogram,
    }


def build_toc_levels(
    rows: list[dict],
    toc_entries: list[list],
) -> dict:
    """Match each TOC entry to a heading row by page + token-overlap.

    Returns {(page_number, line_idx): toc_level} for matched rows.
    """
    by_page_idx: dict[tuple[int, int], int] = {}
    if not toc_entries:
        return {"level_by_row": by_page_idx, "matched": 0, "total": len(rows)}

    rows_by_page: dict[int, list[dict]] = {}
    for r in rows:
        rows_by_page.setdefault(r["page_number"], []).append(r)

    matched = 0
    for entry in toc_entries:
        if len(entry) < 3:
            continue
        toc_level, title, page1 = entry[0], entry[1], entry[2]
        toc_tokens = _tokenize(title)
        if not toc_tokens:
            continue
        for offset in (0, 1, -1):
            page_rows = rows_by_page.get(page1 + offset, [])
            best = None
            best_overlap = 0
            for r in page_rows:
                if (r["page_number"], r["line_idx"]) in by_page_idx:
                    continue
                row_tokens = _tokenize(_strip_md_emphasis(r["text"]))
                overlap = len(toc_tokens & row_tokens)
                if overlap > best_overlap:
                    best, best_overlap = r, overlap
            if best is not None and best_overlap > 0:
                by_page_idx[(best["page_number"], best["line_idx"])] = int(toc_level)
                matched += 1
                break

    return {"level_by_row": by_page_idx, "matched": matched, "total": len(rows)}


def _rewrite_page_md(
    md: str,
    rows_for_page: list[dict],
    level_by_loc: dict[tuple[int, int], int],
    level_by_sig: dict[tuple[float, bool], int] | None = None,
) -> str:
    """Replace each heading line with its sanitised text at its promoted
    level. A line the span oracle resolved to several headings (a merged
    18pt + 13.9pt pair) becomes several lines; parts after the first take
    the level of their own font signature, else one level deeper. An empty
    sanitised heading (pure markup) is dropped.

    Splits/rejoins on ``\\n`` only so any ``\\r`` characters embedded in
    non-heading lines (the SRD's CR-fragmented prose) survive verbatim
    for R1 downstream.
    """
    level_by_sig = level_by_sig or {}
    lines = md.split("\n")
    for r in rows_for_page:
        loc = (r["page_number"], r["line_idx"])
        if not HEADING_RE.match(lines[r["line_idx"]]):
            continue
        parts = r.get("parts") or [(r["text"], r.get("sig"))]
        if not parts or not parts[0][0]:
            lines[r["line_idx"]] = ""
            continue
        first_level = max(1, min(6, int(level_by_loc.get(loc, r["original_level"]))))
        out = [("#" * first_level) + " " + parts[0][0]]
        for text, sig in parts[1:]:
            level = level_by_sig.get(sig, min(6, first_level + 1))
            out.append(("#" * max(1, min(6, int(level)))) + " " + text)
        lines[r["line_idx"]] = "\n".join(out)
    return "\n".join(lines)


def promote_markdown(
    pages: list[dict],
    spans_pages: list[dict],
    toc: dict,
    strategy: str = "font_cluster",
) -> tuple[list[dict], dict]:
    """Apply heading-promotion to a document. Returns (new_pages, report).

    ``strategy`` ∈ {"font_cluster", "toc", "toc_then_font"}.
    """
    if strategy not in {"font_cluster", "toc", "toc_then_font"}:
        raise ValueError(f"unknown strategy: {strategy}")

    rows = collect_heading_signatures(pages, spans_pages)

    font_info = build_font_cluster_levels(rows)
    toc_info = build_toc_levels(rows, toc.get("entries", []) or [])

    level_by_loc: dict[tuple[int, int], int] = {}
    fallback_count = 0
    toc_used = 0
    font_used = 0

    for r in rows:
        loc = (r["page_number"], r["line_idx"])
        new_level: int | None = None

        if strategy in {"toc", "toc_then_font"}:
            if loc in toc_info["level_by_row"]:
                toc_level = toc_info["level_by_row"][loc]
                # toc_then_font only trusts TOC for top-level book structure.
                # Depth ≥ 2 TOC entries don't compose with the chunker's
                # linear heading-stack — they frequently denote leaf items
                # (table titles, sidebars) whose ancestry doesn't match
                # document-linear ancestry.
                if strategy == "toc" or toc_level == 1:
                    new_level = toc_level
                    toc_used += 1

        if new_level is None and strategy in {"font_cluster", "toc_then_font"}:
            sig = r["sig"]
            if sig is not None and sig in font_info["level_by_sig"]:
                new_level = font_info["level_by_sig"][sig]
                font_used += 1

        if new_level is None:
            new_level = r["original_level"]
            fallback_count += 1

        level_by_loc[loc] = new_level

    rows_by_page: dict[int, list[dict]] = {}
    for r in rows:
        rows_by_page.setdefault(r["page_number"], []).append(r)

    new_pages: list[dict] = []
    for page in pages:
        page_rows = rows_by_page.get(page["page_number"], [])
        new_md = _rewrite_page_md(page["markdown"], page_rows, level_by_loc, font_info["level_by_sig"])
        new_pages.append({**page, "markdown": new_md})

    level_distribution = Counter(level_by_loc.values())
    report = {
        "strategy": strategy,
        "n_headings": len(rows),
        "n_unmatched_signature": sum(1 for r in rows if r["sig"] is None),
        "toc_used": toc_used,
        "font_used": font_used,
        "fallback_count": fallback_count,
        "promoted_level_distribution": dict(level_distribution),
        "font_histogram": font_info["histogram"],
        "modal_sig": font_info.get("modal_sig"),
    }
    return new_pages, report

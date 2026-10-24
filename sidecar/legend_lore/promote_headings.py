"""Heading-hierarchy promotion — flat ``##`` → ``#`` / ``##`` / ``###``.

Ported verbatim from heading_hierarchy_spike (Unseen-Servant/unseen-servant-spikes).
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
their original level, floored at 2 — conservative, never destructive,
and never a root (#328: an unmatched ``#`` was how corrupted lines
became breadcrumb roots).
"""
from __future__ import annotations

import re
from collections import Counter

from .heading_text import sanitize

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TOKEN_SPLIT_RE = re.compile(r"\W+", re.UNICODE)
_NUM_RE = re.compile(r"\d+")
_CAPTION_RE = re.compile(r"^(table|figure|fig\.|chart|map|illustration)\s+[\dA-Z][\w.-]*\s*[:.\-–]", re.IGNORECASE)
_URL_RE = re.compile(r"www\.|https?://|\.(com|net|org)\b", re.IGNORECASE)
_SINGLE_LETTER_RE = re.compile(r"\W*[A-Za-z]\W*")
_JUNK_MAX_LEN = 80
# Promoted lines that are not section titles (heading audit, roadmap
# 2026-09-26 §9): a quote attribution ("– Loretta Wineroot, tavern maid"),
# a stat line of Label: value pairs ("Ferocity: 2 Size: Small"), and
# sentences. Question and exclamation headings are real titles ("What Is a
# Spell?", "START PLAYING!"), so only these sentence shapes count: a
# quoted utterance, a lowercase fragment or dialogue ("wights.", "eric:
# These guys have shields?"), a single "Label: value." ("Treasure: None."),
# and prose of four or more words ending in a period.
_ATTRIBUTION_RE = re.compile(r"^[-–—]\s*\S.*,")
_LABEL_VALUE_RE = re.compile(r"[A-Za-z][A-Za-z']*:\s*[^\s:]+")
_SENTENCE_END_RE = re.compile(r"[.!?][\"”’']?$")
_QUOTED_UTTERANCE_RE = re.compile(r"^[\"“].*[.!?][\"”]$")
_LABEL_SENTENCE_RE = re.compile(r"^[A-Za-z][\w ]*:\s+\S")
_PROSE_MIN_WORDS = 4


def _is_sentence(t: str) -> bool:
    if not _SENTENCE_END_RE.search(t):
        return False
    if _QUOTED_UTTERANCE_RE.match(t) or t[:1].islower():
        return True
    if t.endswith("."):
        return bool(_LABEL_SENTENCE_RE.match(t)) or len(t.split()) >= _PROSE_MIN_WORDS
    return False


def is_junk_heading(text: str) -> bool:
    """Shapes that are never section headings (v3 structure.py rule +
    #328's caption/lead-in/URL cases). Stat lines carry ≥ 2 numbers;
    ``Chapter 3`` / ``Level 1 Spells`` keep one. A heading that, stripped
    of non-word characters, is exactly one alphabetic character is junk
    too — OSRIC's drop-cap letters (``I``, ``T``, ``A``) get promoted as
    headings and become spurious breadcrumb roots otherwise; a die code
    (``d6``, ``1d6``) or module code (``B2``) keeps its digits and is not
    junk by this rule."""
    t = text.strip()
    if not t or len(t) > _JUNK_MAX_LEN:
        return True
    if not any(ch.isalpha() for ch in t):
        return True
    if _SINGLE_LETTER_RE.fullmatch(t):
        return True
    if len(_NUM_RE.findall(t)) >= 2:
        return True
    if _CAPTION_RE.match(t) or _URL_RE.search(t) or t.endswith(":"):
        return True
    if _ATTRIBUTION_RE.match(t) or len(_LABEL_VALUE_RE.findall(t)) >= 2:
        return True
    if _is_sentence(t.strip("*_ ")):
        return True
    return False


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


def build_font_cluster_levels(rows: list[dict], min_root_count: int = 2) -> dict:
    """Map each (size, bold) signature → promoted level.

    Modal cluster stays at level 2; larger clusters get level 1 (top
    cluster) or level 2 (the rest); smaller clusters get distinct
    descending levels 3, 4, 5, 6 (capped at 6). A signature seen fewer
    than ``min_root_count`` times cannot own level 1 — a one-off larger
    signature (a front-matter footer, say) is demoted to level 2 rather
    than crowning it the root; the top cluster with ≥ ``min_root_count``
    rows takes level 1 instead.
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

    eligible = [s for s in larger_than_modal if hist[s] >= min_root_count]
    root = eligible[0] if eligible else None
    for s in larger_than_modal:
        level_by_sig[s] = 1 if s == root else 2

    level_by_sig[modal_sig] = 2

    for k, s in enumerate(smaller_than_modal):
        level_by_sig[s] = min(6, 3 + k)

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

    Levels are relative to the *effective* top depth — the shallowest
    depth with ≥ 2 entries (a lone depth-1 book title doesn't count as
    the book's real top level; falls back to the shallowest depth
    present when no depth has 2+ entries). An entry at the effective
    depth reports level 1; entries shallower than it (the lone book
    title) are skipped.

    Returns {(page_number, line_idx): relative_level} for matched rows,
    plus the effective depth used.
    """
    by_page_idx: dict[tuple[int, int], int] = {}
    if not toc_entries:
        return {"level_by_row": by_page_idx, "matched": 0, "total": len(rows), "effective_depth": 1}

    depth_counts = Counter(int(e[0]) for e in toc_entries if len(e) >= 3)
    effective_depth = next((d for d in sorted(depth_counts) if depth_counts[d] >= 2),
                           min(depth_counts) if depth_counts else 1)

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
                rel = int(toc_level) - effective_depth + 1
                if rel >= 1:
                    by_page_idx[(best["page_number"], best["line_idx"])] = rel
                    matched += 1
                break

    return {"level_by_row": by_page_idx, "matched": matched, "total": len(rows),
            "effective_depth": effective_depth}


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
    sanitised heading (pure markup) is dropped. Junk is decided PER PART
    (a stat line merged with a real heading on one line must not lose the
    real heading, nor let a junk part downstream slip through as one): the
    first part uses the row-level ``r["junk"]`` (also what gates the font
    histogram), later parts are judged independently via
    ``is_junk_heading``; a junk part is emitted as a bold paragraph line,
    a non-junk part as a heading line — the first non-junk part at
    ``first_level``, later non-junk parts at their own font signature's
    level (else one level deeper).

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
        first_level = max(1, min(MAX_LEVEL, int(level_by_loc.get(loc, r["original_level"]))))
        out = []
        first_heading_done = False
        for i, (text, sig) in enumerate(parts):
            is_junk_part = r.get("junk") if i == 0 else is_junk_heading(text)
            if is_junk_part:
                out.append(f"**{text}**")
                continue
            if not first_heading_done:
                level = first_level
                first_heading_done = True
            else:
                level = level_by_sig.get(sig, min(MAX_LEVEL, first_level + 1))
            out.append(("#" * max(1, min(MAX_LEVEL, int(level)))) + " " + text)
        lines[r["line_idx"]] = "\n".join(out)
    return "\n".join(lines)


# ─────────────── outline strategy ───────────────
# docs/retrieval/2026-09-27-outline-headings-design.md: the publisher's PDF
# outline supplies the heading structure when the book has a trustworthy
# one; font-detected headings only add detail inside an outline entry.

# Deepest heading level written to the page Markdown: outline depth plus
# the font clusters shifted below it (the chunker and cleanup read up to
# this many '#').
MAX_LEVEL = 12
# Trust gate (§3.1), measured on a 3,293-PDF collection (§2.1).
OUTLINE_MIN_ENTRIES = 5
OUTLINE_MIN_PLACED = 0.70
OUTLINE_MIN_SPAN = 0.50
# Placement (§3.2): share of the title's tokens a line must hold, and the
# longest body line that may be promoted (a title, not a sentence using it).
PLACE_MIN_OVERLAP = 0.5
PROMOTE_MAX_WORDS = 12
# Editorial label outlines put before box titles ("NPC: Master Ulvar",
# "Table: Rumors"); the page does not print it.
_BOX_PREFIX_RE = re.compile(r"^\s*[A-Za-z]+(?:\s[A-Za-z]+)?\s*:\s*(?=\S)")
_TABLE_WORD_RE = re.compile(r"\btable\b", re.IGNORECASE)
_BODY_MARKUP_RE = re.compile(r"^[\s>*_\-•·]+|[*_]+")


def outline_entries(toc_entries: list[list]) -> list[dict]:
    """Outline entries relative to the book's effective top depth (the
    same rule as ``build_toc_levels``: a lone book-title entry above the
    real top level is skipped). Each: level, title (label prefix
    stripped), page, box (a leaf that must never parent what follows)."""
    entries = [e for e in toc_entries if len(e) >= 3]
    if not entries:
        return []
    depths = Counter(int(e[0]) for e in entries)
    top = next((d for d in sorted(depths) if depths[d] >= 2), min(depths))
    out = []
    for depth, title, page in ((int(e[0]), str(e[1]), int(e[2])) for e in entries):
        level = depth - top + 1
        if level < 1:
            continue
        stripped = _BOX_PREFIX_RE.sub("", title).strip()
        box = stripped != title.strip() or bool(_TABLE_WORD_RE.search(title))
        out.append({"level": level, "title": stripped, "page": page, "box": box})
    return out


def _overlap(want: set[str], have: set[str]) -> float:
    return len(want & have) / len(want) if want else 0.0


def place_outline(rows: list[dict], pages: list[dict], entries: list[dict]) -> dict:
    """Place each outline entry on its page, the next, or the previous.

    On each page, in that order: a detected heading row holding at least
    ``PLACE_MIN_OVERLAP`` of the title's tokens is claimed (best overlap
    wins); else a short body line is (an entry font detection missed —
    a heading is inserted above it); else the next page is tried. An
    entry found nowhere is left unplaced rather than put anywhere.
    """
    rows_by_page: dict[int, list[dict]] = {}
    for r in rows:
        rows_by_page.setdefault(r["page_number"], []).append(r)
    md_by_page = {p["page_number"]: p["markdown"] for p in pages}
    claimed: set[tuple[int, int]] = set()
    row_entry: dict[tuple[int, int], dict] = {}
    inserts: dict[tuple[int, int], dict] = {}
    body_cache: dict[int, list[tuple[int, set[str], int]]] = {}

    def body_lines(page: int) -> list[tuple[int, set[str], int]]:
        if page not in body_cache:
            out = []
            for i, line in enumerate(md_by_page.get(page, "").split("\n")):
                if not line.strip() or HEADING_RE.match(line) or line.lstrip().startswith("|"):
                    continue
                text = _BODY_MARKUP_RE.sub("", line).strip()
                out.append((i, _tokenize(text), len(text.split())))
            body_cache[page] = out
        return body_cache[page]

    existing = promoted = 0
    for e in entries:
        want = _tokenize(e["title"])
        if not want:
            continue
        for page in (e["page"], e["page"] + 1, e["page"] - 1):
            best = None
            for r in rows_by_page.get(page, []):
                loc = (r["page_number"], r["line_idx"])
                if loc in claimed:
                    continue
                ov = _overlap(want, _tokenize(_strip_md_emphasis(r["text"])))
                if ov >= PLACE_MIN_OVERLAP and (best is None or ov > best[0]):
                    best = (ov, loc)
            if best is not None:
                claimed.add(best[1])
                row_entry[best[1]] = e
                existing += 1
                break
            best_line = None
            for i, toks, words in body_lines(page):
                loc = (page, i)
                if loc in claimed or words > PROMOTE_MAX_WORDS:
                    continue
                ov = _overlap(want, toks)
                if ov >= PLACE_MIN_OVERLAP and (
                    best_line is None or (ov, -words) > (best_line[0], -best_line[1])
                ):
                    best_line = (ov, words, loc)
            if best_line is not None:
                claimed.add(best_line[2])
                inserts[best_line[2]] = e
                promoted += 1
                break
    considered = [e for e in entries if _tokenize(e["title"])]
    return {
        "row_entry": row_entry,
        "inserts": inserts,
        "considered": len(considered),
        "existing": existing,
        "promoted": promoted,
        "unplaced": len(considered) - existing - promoted,
        "boxes": sum(1 for e in considered if e["box"]),
        "pages": [e["page"] for e in considered],
    }


def outline_trusted(placement: dict, page_count: int) -> tuple[bool, float, float]:
    """The trust gate: (trusted, placed rate, span as a share of the book)."""
    n = placement["considered"]
    placed = (placement["existing"] + placement["promoted"]) / n if n else 0.0
    pages = placement["pages"]
    span = (max(pages) - min(pages) + 1) / page_count if pages and page_count else 0.0
    trusted = n >= OUTLINE_MIN_ENTRIES and placed >= OUTLINE_MIN_PLACED and span >= OUTLINE_MIN_SPAN
    return trusted, placed, span


def _junk_part_count(r: dict) -> int:
    """Count the junk parts within a (possibly merged) heading row, per
    the same per-part rule ``_rewrite_page_md`` uses: first part via
    ``r["junk"]``, later parts via ``is_junk_heading``. A row whose parts
    are empty (dropped upstream, never emitted as any line) counts 0."""
    parts = r.get("parts") or [(r["text"], r.get("sig"))]
    if not parts or not parts[0][0]:
        return 0
    return sum(
        1
        for i, (text, _sig) in enumerate(parts)
        if (r["junk"] if i == 0 else is_junk_heading(text))
    )


def promote_markdown(
    pages: list[dict],
    spans_pages: list[dict],
    toc: dict,
    strategy: str = "font_cluster",
) -> tuple[list[dict], dict]:
    """Apply heading-promotion to a document. Returns (new_pages, report).

    ``strategy`` ∈ {"font_cluster", "toc", "toc_then_font", "outline"}.
    ``outline`` uses the PDF outline when it passes the trust gate and
    falls back to ``toc_then_font`` otherwise (the report says which).
    """
    if strategy not in {"font_cluster", "toc", "toc_then_font", "outline"}:
        raise ValueError(f"unknown strategy: {strategy}")

    rows = collect_heading_signatures(pages, spans_pages)

    for r in rows:
        r["junk"] = is_junk_heading(r["text"])

    outline_report: dict = {}
    if strategy == "outline":
        entries = outline_entries(toc.get("entries", []) or [])
        placement = place_outline(rows, pages, entries)
        page_count = max((p["page_number"] for p in pages), default=0)
        trusted, placed_rate, span = outline_trusted(placement, page_count)
        outline_report = {
            "outline_trusted": trusted,
            "outline_entries": placement["considered"],
            "outline_placed": round(placed_rate, 3),
            "outline_span": round(span, 3),
            "outline_existing": placement["existing"],
            "outline_promoted": placement["promoted"],
            "outline_unplaced": placement["unplaced"],
            "outline_boxes": placement["boxes"],
        }
        if trusted:
            return _promote_by_outline(pages, rows, placement, outline_report)
        strategy = "toc_then_font"

    font_info = build_font_cluster_levels([r for r in rows if not r["junk"]])
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
            new_level = max(2, r["original_level"])
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
        "junk_demoted": sum(_junk_part_count(r) for r in rows),
        "promoted_level_distribution": dict(level_distribution),
        "font_histogram": font_info["histogram"],
        "modal_sig": font_info.get("modal_sig"),
        "toc_effective_depth": toc_info["effective_depth"],
        **outline_report,
    }
    return new_pages, report


def _promote_by_outline(
    pages: list[dict], rows: list[dict], placement: dict, outline_report: dict,
) -> tuple[list[dict], dict]:
    """Levels under a trusted outline (§3.3).

    An outline entry at relative depth *d* is level *d*; a box entry is
    the deepest level in use, so any following heading closes it.
    Detected headings the outline does not list keep their font-cluster
    order shifted below the outline, so the next outline entry always
    closes them. An outline-placed line is never demoted as junk.
    """
    row_entry, inserts = placement["row_entry"], placement["inserts"]
    placed = list(row_entry.values()) + list(inserts.values())
    depth = max((e["level"] for e in placed if not e["box"]), default=1)
    box_level = min(MAX_LEVEL, depth + 6)

    def entry_level(e: dict) -> int:
        return box_level if e["box"] else min(MAX_LEVEL, e["level"])

    font_info = build_font_cluster_levels(
        [r for r in rows if not r["junk"] and (r["page_number"], r["line_idx"]) not in row_entry]
    )
    shifted_by_sig = {
        sig: min(MAX_LEVEL, depth + lvl) for sig, lvl in font_info["level_by_sig"].items()
    }
    level_by_loc: dict[tuple[int, int], int] = {}
    for r in rows:
        loc = (r["page_number"], r["line_idx"])
        if loc in row_entry:
            r["junk"] = False
            level_by_loc[loc] = entry_level(row_entry[loc])
        elif r["sig"] is not None and r["sig"] in shifted_by_sig:
            level_by_loc[loc] = shifted_by_sig[r["sig"]]
        else:
            level_by_loc[loc] = min(MAX_LEVEL, depth + max(2, r["original_level"]))

    rows_by_page: dict[int, list[dict]] = {}
    for r in rows:
        rows_by_page.setdefault(r["page_number"], []).append(r)
    inserts_by_page: dict[int, list[tuple[int, dict]]] = {}
    for (page, idx), e in inserts.items():
        inserts_by_page.setdefault(page, []).append((idx, e))

    new_pages: list[dict] = []
    for page in pages:
        md = _rewrite_page_md(
            page["markdown"], rows_by_page.get(page["page_number"], []),
            level_by_loc, shifted_by_sig,
        )
        if page["page_number"] in inserts_by_page:
            lines = md.split("\n")
            for idx, e in inserts_by_page[page["page_number"]]:
                lines[idx] = "#" * entry_level(e) + " " + e["title"] + "\n" + lines[idx]
            md = "\n".join(lines)
        new_pages.append({**page, "markdown": md})

    levels = list(level_by_loc.values()) + [entry_level(e) for e in inserts.values()]
    report = {
        "strategy": "outline",
        "n_headings": len(rows) + len(inserts),
        "n_unmatched_signature": sum(1 for r in rows if r["sig"] is None),
        "toc_used": len(row_entry) + len(inserts),
        "font_used": sum(1 for r in rows if (r["page_number"], r["line_idx"]) not in row_entry),
        "fallback_count": 0,
        "junk_demoted": sum(_junk_part_count(r) for r in rows),
        "promoted_level_distribution": dict(Counter(levels)),
        "font_histogram": font_info["histogram"],
        "modal_sig": font_info.get("modal_sig"),
        "toc_effective_depth": depth,
        **outline_report,
    }
    return new_pages, report

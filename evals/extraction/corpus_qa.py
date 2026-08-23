"""Corpus-wide extraction QA — every page, the PDF as the oracle (W0.1 of
docs/roadmap/2026-08-22-v3-search-recovery-strategy.md).

The golden-page suite grades 30 hand-picked pages as a mean; the defect that
broke the v3 blind round (columns interleaved, stat-block labels torn from
their values) lived on ~27% of pages and never tripped it. This axis needs no
spec: PyMuPDF's native text blocks are column-correct on those pages, so a
native block that is *present but not contiguous* in the engine's page text
is an interleave, by construction. Engine-agnostic (v2 and v3 both expose
per-page text through ``Engine.extract``); no embedding, minutes per corpus.

Per page:
- blocks / intact / broken / missing — native blocks of ≥ MIN_BLOCK_CHARS:
  intact = contiguous in the page text; broken = most of its lines present
  but not contiguous (the interleave signature); missing = dropped (running
  headers and footers are dropped on purpose — recall, not integrity).
- label_lines / label_intact — native lines that open with a stat-block or
  spell label ("Armor Class", "Range:", …) and survive whole. Stat fields are
  one-line blocks, below the size floor, so they get their own count.
- empty — the engine emitted < 10 % of the page's native text (≥ 200 chars):
  the layout stage found no content region (only a footer) and dropped the
  whole page — 33 corpus pages on 2026-08-22, invisible to every other count.
- adjacent_pairs / adjacent_ok — consecutive native blocks stacked in one
  column (same left edge, a line or so apart) that are still consecutive in
  the page text. Catches *displacement*: the goblin's "Armor Class 15" line
  surviving intact but glued onto the gnoll's Spear action, which neither
  contiguity nor label checks can see.

Comparison is on text with all non-alphanumerics removed, so hyphenation,
markdown emphasis, pipe cells and whitespace litter never count as breaks.
"""
from __future__ import annotations

from collections import defaultdict
from typing import NamedTuple

from evals.retrieval.grade import normalize

MIN_BLOCK_CHARS = 120   # squeezed chars; table cells and stat fields sit below this
MIN_LINE_CHARS = 8
STAT_LABELS = ("armor class", "hit points", "speed", "challenge",
               "casting time", "range", "duration", "saving throw", "components")

KEY_CHARS = 24          # tail/head key length for the adjacency check
ADJ_SLACK = 40          # squeezed chars allowed between a block's tail and its neighbour's head
STACK_DX, STACK_DY = 15.0, 18.0   # same left edge; vertical gap ≤ ~1.5 lines

EMPTY_MIN_NATIVE, EMPTY_RATIO = 200, 0.1   # a page with real text that came out (nearly) blank

METRICS = ["block_integrity", "block_recall", "label_integrity", "adjacency"]


class NativeBlock(NamedTuple):
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def _squeeze(text: str) -> str:
    return normalize(text).replace(" ", "")


def native_blocks(page) -> list[NativeBlock]:
    """PyMuPDF text blocks of one page, in the PDF's own order, with bboxes."""
    return [NativeBlock(b[4], b[0], b[1], b[2], b[3])
            for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]


def _stacked(a: NativeBlock, b: NativeBlock) -> bool:
    return abs(b.x0 - a.x0) <= STACK_DX and -2.0 <= b.y0 - a.y1 <= STACK_DY


def _still_adjacent(hay: str, a: NativeBlock, b: NativeBlock) -> bool | None:
    """None = not judgeable (a key too short, or a side absent — a dropped block
    is recall, not displacement); else whether b's head follows a's tail."""
    tail, head = _squeeze(a.text)[-KEY_CHARS:], _squeeze(b.text)[:KEY_CHARS]
    if len(tail) < MIN_LINE_CHARS or len(head) < MIN_LINE_CHARS:
        return None
    if tail not in hay or head not in hay:
        return None
    i = hay.find(tail)
    while i >= 0:
        j = hay.find(head, i + len(tail))
        if 0 <= j <= i + len(tail) + ADJ_SLACK:
            return True
        i = hay.find(tail, i + 1)
    return False


def grade_page(page_text: str, blocks: list[NativeBlock], labels=STAT_LABELS,
               min_chars: int = MIN_BLOCK_CHARS) -> dict:
    hay = _squeeze(page_text)
    n = intact = broken = missing = 0
    for b in blocks:
        sq = _squeeze(b.text)
        if len(sq) < min_chars:
            continue
        n += 1
        if sq in hay:
            intact += 1
            continue
        lines = [_squeeze(l) for l in b.text.splitlines()]
        lines = [l for l in lines if len(l) >= MIN_LINE_CHARS]
        found = sum(1 for l in lines if l in hay)
        if lines and found * 2 >= len(lines):
            broken += 1
        else:
            missing += 1
    label_lines = label_intact = 0
    for b in blocks:
        for line in b.text.splitlines():
            norm = normalize(line)
            if not any(norm.startswith(lab) and len(norm) > len(lab) for lab in labels):
                continue
            label_lines += 1
            label_intact += _squeeze(line) in hay
    pairs = ok = 0
    for a, b in zip(blocks, blocks[1:]):
        if not _stacked(a, b):
            continue
        adj = _still_adjacent(hay, a, b)
        if adj is None:
            continue
        pairs += 1
        ok += adj
    native_chars = sum(len(_squeeze(b.text)) for b in blocks)
    return {"blocks": n, "intact": intact, "broken": broken, "missing": missing,
            "label_lines": label_lines, "label_intact": label_intact,
            "adjacent_pairs": pairs, "adjacent_ok": ok,
            "native_chars": native_chars, "engine_chars": len(hay),
            "empty": native_chars >= EMPTY_MIN_NATIVE and len(hay) < EMPTY_RATIO * native_chars}


def aggregate(pages: list[dict]) -> dict[str, dict]:
    """Per-doc rollup plus 'all'. Integrity is over blocks that are present
    (dropping furniture is not an interleave); recall is over all blocks."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        buckets[p["doc"]].append(p)
        buckets["all"].append(p)
    out: dict[str, dict] = {}
    for doc, rows in buckets.items():
        tot = {k: sum(r.get(k, 0) for r in rows)
               for k in ("blocks", "intact", "broken", "missing", "label_lines", "label_intact",
                         "adjacent_pairs", "adjacent_ok")}
        present = tot["intact"] + tot["broken"]
        out[doc] = {
            "pages": len(rows),
            **tot,
            "block_integrity": tot["intact"] / present if present else None,
            "block_recall": present / tot["blocks"] if tot["blocks"] else None,
            "label_integrity": tot["label_intact"] / tot["label_lines"] if tot["label_lines"] else None,
            "adjacency": tot["adjacent_ok"] / tot["adjacent_pairs"] if tot["adjacent_pairs"] else None,
            "pages_with_broken": sum(1 for r in rows if r.get("broken", 0) > 0),
            "pages_empty": sum(1 for r in rows if r.get("empty")),
        }
    return out


def _torn(p: dict) -> int:
    return p.get("label_lines", 0) - p.get("label_intact", 0)


def _displaced(p: dict) -> int:
    return p.get("adjacent_pairs", 0) - p.get("adjacent_ok", 0)


def empty_pages(pages: list[dict]) -> list[dict]:
    """Pages that came out blank — listed apart so they never crowd out the
    interleave list (33 of them on 2026-08-22)."""
    return [p for p in pages if p.get("empty")]


def worst_pages(pages: list[dict], n: int = 20) -> list[dict]:
    bad = [p for p in pages
           if not p.get("empty") and (p.get("broken", 0) > 0 or _torn(p) > 0 or _displaced(p) > 0)]
    return sorted(bad, key=lambda p: (-(p.get("broken", 0) + _displaced(p)), -_torn(p),
                                      p["doc"], p["page"]))[:n]


def format_report(summary: dict[str, dict]) -> str:
    header = (f"{'doc':<16}{'pages':>7}{'blocks':>8}{'broken':>8}{'missing':>8}"
              f"{'pages_w_broken':>16}{'pages_empty':>13}" + "".join(f"{m:>17}" for m in METRICS))
    lines = [header, "-" * len(header)]
    for doc in sorted(d for d in summary if d != "all") + ["all"]:
        r = summary[doc]
        cells = "".join(
            f"{(format(r[m], '.3f') if r.get(m) is not None else '—'):>17}" for m in METRICS)
        lines.append(f"{doc:<16}{r['pages']:>7}{r['blocks']:>8}{r['broken']:>8}{r['missing']:>8}"
                     f"{r['pages_with_broken']:>16}{r['pages_empty']:>13}" + cells)
    return "\n".join(lines)


def render_md(meta: dict, result: dict) -> str:
    empty = [f"- {p['doc']} p.{p['page']}: {p.get('engine_chars', 0)} of {p.get('native_chars', 0)} chars emitted"
             for p in result.get("empty", [])]
    worst = [
        f"- {p['doc']} p.{p['page']}: {p['broken']}/{p['blocks']} blocks broken, "
        f"{_displaced(p)}/{p.get('adjacent_pairs', 0)} neighbours displaced, {_torn(p)} label lines torn"
        for p in result["worst"]
    ]
    return "\n".join([
        f"# Corpus extraction QA — {meta['engine']} — {meta['name']}",
        "", f"Date: {meta['date']}",
        f"Pages: {len(result['pages'])}  |  oracle: PyMuPDF native text blocks (≥{MIN_BLOCK_CHARS} chars)",
        "", "## By doc", "```", format_report(result["by_doc"]), "```",
        "", f"## Empty pages ({len(empty)})", *empty,
        "", f"## Worst pages ({len(worst)})", *worst, "",
    ])

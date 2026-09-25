"""Breadcrumb QA — is the section heading that feeds the embedding and the
reranker a usable topical label? (roadmap 2026-09-02 §1.5, Phase 0.2)

Measured by hand on the 08-15 v2 results: 84 % of returned chunks carried
Markdown markup in the breadcrumb, 27 % were rooted at OSRIC's running
footer, 11 % at the split word "S eed p" (= Speed). ``section_heading`` is
prepended to the embedded text (``chunker._embed_text``) and to the
cross-encoder input (``service._search_sync``), so damage here is a retrieval
defect. This axis grades every chunk the chunker produces — no embedding,
seconds per corpus — and is the gate Phase 1's heading work must clear.

Per chunk, a set of flaws:
- markup         — Markdown/HTML emphasis survived into the heading
- split_letter   — a letter stranded off a word ("Dexterit y", "S eed p")
- mixed_case     — small-caps font damage ("chaRacteR RaceS")
- furniture_root — the breadcrumb root is page furniture (running footer,
                   CONTENTS, a URL), not a section
- no_heading     — the chunk has no breadcrumb at all
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

FLAWS = ["markup", "split_letter", "mixed_case", "furniture_root", "no_heading"]

# Emphasis (any run of * or _ at a word edge), inline HTML, backticks, and a
# leading Markdown heading marker. An underscore inside a word (snake_case
# names in some indie titles) is not markup.
_MARKUP = re.compile(r"\*+|(?<!\w)_+|_+(?!\w)|</?[a-z][a-z0-9]*(?:\s[^>]*)?>|`|^#+\s*")
# A stranded single letter, excluding the legitimate ones ("a", "I"). A
# letter joined to its neighbour by a hyphen/dash (A–Z, MM-B, Will-o'-Wisp),
# an apostrophe (NATURE'S, Player's), or followed by % (die notation d%) is
# part of a word, not stranded. Matching the split ("word space short-word")
# finds ordinary English like "a pit".
_JOINERS = "\\w'\u2019\\-\u2010\u2011\u2012\u2013\u2014\u00ad"
_LONE_LETTER = re.compile(
    rf"(?<![{_JOINERS}])(?![aAI](?![{_JOINERS}]))[A-Za-z](?![{_JOINERS}%])"
)
# A lowercase run followed by an uppercase letter inside one word: a small-caps
# display font read back as mixed case. "THAC0" (all caps) does not match.
_MIXED_CASE = re.compile(r"\b[a-z]+[A-Z][A-Za-z]*\b")
_FURNITURE = re.compile(
    r"\bcontents\b|\berrata\b|for free updates|\bvisit:?\b|www\.|https?://|\bpage \d+\b",
    re.IGNORECASE,
)


def strip_markup(heading: str) -> str:
    return _MARKUP.sub("", heading or "").strip()


def root_of(heading: str) -> str:
    """The first breadcrumb segment, markup stripped."""
    return strip_markup((heading or "").split(" > ", 1)[0])


def flaws(heading: str | None) -> set[str]:
    if not heading or not heading.strip():
        return {"no_heading"}
    out: set[str] = set()
    if _MARKUP.search(heading):
        out.add("markup")
    clean = strip_markup(heading)
    if _LONE_LETTER.search(clean):
        out.add("split_letter")
    if _MIXED_CASE.search(clean):
        out.add("mixed_case")
    if _FURNITURE.search(root_of(heading)):
        out.add("furniture_root")
    return out


def grade_doc(doc_id: str, chunks: list[dict], top_n: int = 5) -> dict:
    """Flaw counts over one document's chunks, plus its most common roots."""
    counts = Counter()
    roots = Counter()
    for c in chunks:
        h = c.get("section_heading")
        counts.update(flaws(h))
        if h:
            roots[root_of(h)] += 1
    return {"doc": doc_id, "chunks": len(chunks), **{f: counts[f] for f in FLAWS},
            "top_roots": roots.most_common(top_n)}


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """Per-doc rollup plus 'all'; every flaw as a count and a rate."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r["doc"]].append(r)
        buckets["all"].append(r)
    out: dict[str, dict] = {}
    for doc, rs in buckets.items():
        n = sum(r["chunks"] for r in rs)
        row = {"chunks": n}
        for f in FLAWS:
            k = sum(r[f] for r in rs)
            row[f] = k
            row[f"{f}_rate"] = k / n if n else None
        out[doc] = row
    return out


def residue(chunks: list[dict], per_flaw: int = 8) -> dict[str, list[tuple[str, int]]]:
    """Per flaw, the most frequent headings that carry it — what a fix
    would have to handle next. Keys are every flaw, empty when clean."""
    counts: dict[str, Counter] = {f: Counter() for f in FLAWS}
    for c in chunks:
        h = c.get("section_heading")
        for f in flaws(h):
            counts[f][h or ""] += 1
    return {f: counts[f].most_common(per_flaw) for f in FLAWS}


def regressions(current: dict, reference: dict) -> list[dict]:
    """Fail closed: any per-doc flaw count that rose vs the reference."""
    out = []
    for doc, ref in reference.items():
        cur = current.get(doc)
        if cur is None:
            continue
        for f in FLAWS:
            if f in ref and f in cur and cur[f] > ref[f]:
                out.append({"doc": doc, "flaw": f, "ref": ref[f], "cur": cur[f]})
    return out


def format_report(summary: dict[str, dict]) -> str:
    header = f"{'doc':<16}{'chunks':>8}" + "".join(f"{f + '_rate':>20}" for f in FLAWS)
    lines = [header, "-" * len(header)]
    for doc in sorted(d for d in summary if d != "all") + ["all"]:
        r = summary[doc]
        cells = "".join(
            f"{(format(r[f + '_rate'], '.3f') if r.get(f + '_rate') is not None else '—'):>20}"
            for f in FLAWS)
        lines.append(f"{doc:<16}{r['chunks']:>8}" + cells)
    return "\n".join(lines)


def render_md(meta: dict, result: dict) -> str:
    roots = []
    for r in result["docs"]:
        roots.append(f"- **{r['doc']}** ({r['chunks']} chunks): "
                     + "; ".join(f"`{root[:60]}` ×{n}" for root, n in r["top_roots"]))
    lines = [
        f"# Breadcrumb QA — {meta['engine']} — {meta['name']}",
        "", f"Date: {meta['date']}",
        "Unit: every chunk the chunker emits; flaw = property of its section_heading",
        "", "## By doc", "```", format_report(result["by_doc"]), "```",
        "", "## Top roots per doc", *roots, "",
    ]
    if result.get("residue"):
        lines += ["", "## Residue (most frequent flawed headings per doc)"]
        for doc, per_flaw in result["residue"].items():
            items = [(f, h, n) for f, rows in per_flaw.items() for h, n in rows]
            if not items:
                continue
            lines.append(f"- **{doc}**: " + "; ".join(
                f"{f}: `{h}` ×{n}" for f, h, n in items[:12]))
    return "\n".join(lines)

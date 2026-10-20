"""
Legend Lore — indexing and search engine behind the sidecar routes.

PDF extraction, chunking and embedding into the library store, the
manifest and collection stores, sync diffing, and the search pipeline. The HTTP surface over it is ``router.py``; app construction
and process lifecycle stay in ``sidecar/server.py``.
"""

import hashlib
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath

import pymupdf
import pymupdf4llm
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

from .chunker import (
    PIPELINE_VERSION,
    Chunk,
    PageMarkdown,
    structure_aware,
)
from .cleanup import clean_pages
from .promote_headings import promote_markdown
from .granularity import EmbedUnit, ParentDoc, build as build_granularity
from .library_store import LibraryStore
from .parents_store import fetch_parents, fetch_sections, section_root_for
from .lexical import (
    LEXICAL_RERANK_POOL, LEXICAL_RRF_WEIGHT, rrf_fuse,
)
from .near_dup import collapse_near_dups
from .reranker import rerank_scores
from .spelling import keyword_tokens, trailing_token


# Number of top dense candidates to feed into the cross-encoder. Set
# to balance re-rank latency against the size of the candidate pool the
# parent-dedupe loop sees in re-ranked order. Trailing candidates beyond
# this still appear (in cosine order) so dedupe never starves.
RERANK_CANDIDATE_POOL = int(os.getenv("RERANK_CANDIDATES", "50"))

# Bounds for the user-tunable rerank pool size (search settings / per-request
# override). Below 10 the reranker can't reorder a first page; above 200 the
# per-doc cross-encoder cost makes search unusably slow.
RERANK_POOL_MIN = 10
RERANK_POOL_MAX = 200


# Relevance-tier thresholds (issues #306/#310). Neither score scale is a
# calibrated probability, so results carry an ordinal tier instead of a
# raw percentage. Thresholds are scale-specific:
# - Rerank scale is the cross-encoder sigmoid, which saturates: fit
#   2026-09-24 (roadmap 3.4, #366) on the int8 L-6 against the headings
#   blind-round labels carried onto `2026-09-24-v2-rerank` (238 top-5
#   results): human precision is 73% at ≥ 0.98, 32% in 0.5–0.98 and 12%
#   below 0.5 (the old 0.5 strong line held 55%). On the real library
#   (6 books, `sidecar/evals/library_probe.py`) that is 27% strong,
#   29% good, 44% weak — was 56% strong. 0.99 was stricter (81%) but
#   demoted correct top hits such as 5e Grappling to "good".
# - Cosine scale is bge-m3 similarity; defaults calibrated against the
#   hybrid_retrieval_spike ground truth (V0_h, 200 labeled results):
#   below 0.50 only 12.5% of results are correct (1 correct result
#   demoted); at/above 0.60 precision is 66% vs a 53% base rate. bge-m3
#   cosine lives in a compressed [0.45, 0.76] band — never near 0 or 1.
# The weak threshold is the "relevance floor": weak results are still
# returned (recall preserved) but demoted in the UI and flagged to MCP
# clients so out-of-scope queries stop looking confidently answered.
RERANK_TIER_STRONG = float(os.getenv("RERANK_TIER_STRONG", "0.98"))
RERANK_TIER_WEAK = float(os.getenv("RERANK_TIER_WEAK", "0.5"))
COSINE_TIER_STRONG = float(os.getenv("COSINE_TIER_STRONG", "0.60"))
COSINE_TIER_WEAK = float(os.getenv("COSINE_TIER_WEAK", "0.50"))


# ---------------------------------------------------------------------------
# Pure helpers (no dependencies — safe to import in tests)
# ---------------------------------------------------------------------------

from .game_systems import GAME_SYSTEMS, KNOWN_SYSTEMS

import unicodedata


def _normalize_for_match(s: str) -> str:
    """Lowercase, decompose accents, fold ``&`` to ``n``, drop non-alphanum.

    The goal is that a keyword like ``"d&d 5e"`` matches paths or content
    written as ``"D&D 5E"``, ``"DnD 5e"``, ``"d&d-5e"``, ``"dnd_5e"``, or
    ``"Mörk Borg"`` all the same. Both the haystack and the needle go
    through this helper before substring matching.
    """
    # NFKD splits ``ö`` into ``o`` + combining diaeresis; the combining
    # codepoint is then dropped along with all other non-alphanum below.
    s = unicodedata.normalize("NFKD", s).lower()
    # ``d&d`` and ``dnd`` collide cleanly when ``&`` becomes ``n``.
    s = s.replace("&", "n")
    return "".join(ch for ch in s if ch.isalnum())


def _resolve_filter_value(
    value: str, candidates: list[str]
) -> tuple[str | None, list[str]]:
    """Resolve a user/agent-supplied filter value against known candidates.

    MCP agents guess filter values from user vernacular ("dnd 5e",
    "Players Handbook.pdf"), so exact-match-or-nothing turns every
    near-miss into a silent empty result (issue #309). Resolution order:
    exact match; case/accent-insensitive equality; unique normalized
    substring (either direction, so "D&D" finds "D&D 5E" and
    "dragonbane monsters" finds "dragonbane_monsters.pdf").

    Returns ``(resolved, matches)``: ``resolved`` is the single
    unambiguous candidate or ``None``; ``matches`` carries the
    candidates that partially matched, for building hint messages.
    """
    if value in candidates:
        return value, [value]
    needle = _normalize_for_match(value)
    if not needle:
        return None, []
    normalized = {c: _normalize_for_match(c) for c in candidates}
    equal = [c for c, n in normalized.items() if n == needle]
    if len(equal) == 1:
        return equal[0], equal
    if equal:
        return None, equal
    substring = [
        c for c, n in normalized.items() if needle in n or n in needle
    ]
    if len(substring) == 1:
        return substring[0], substring
    return None, substring


def _rerank_safe_for_query(query: str) -> bool:
    """Whether the bundled cross-encoder should be trusted for this query.

    The default reranker (ms-marco-MiniLM) is English-only; on non-English
    queries it emits noise scores that invert bge-m3's genuinely
    multilingual cosine ranking (a correct French section gets demoted out
    of the visible top results). An all-ASCII query is treated as
    English-and-safe; a query with accented/non-Latin characters skips
    reranking so the dense order is preserved. Conservative by design — it
    never reranks-away a non-English query, and never changes English
    behaviour (issue #305).
    """
    return query.isascii()


def _tier_for(relevance: float, reranked: bool) -> str:
    """Ordinal relevance tier for a result, on its own score scale.

    ``relevance`` is the response-shape value (1 - distance, clamped to
    [0, 1]): the cross-encoder sigmoid when the result was reranked,
    bge-m3 cosine similarity otherwise.
    """
    strong = RERANK_TIER_STRONG if reranked else COSINE_TIER_STRONG
    weak = RERANK_TIER_WEAK if reranked else COSINE_TIER_WEAK
    if relevance >= strong:
        return "strong"
    if relevance >= weak:
        return "good"
    return "weak"


def pack_results(results: list[dict], budget: int | None) -> list[dict]:
    """Fill in rank order under a character budget; the first result that
    does not fit is cut to its matched unit (if that fits) and ends the list."""
    if budget is None:
        return [{**r, "truncated": False} for r in results]
    out: list[dict] = []
    used = 0
    for r in results:
        cost = len(r["text"]) + len(r["section_heading"])
        if used + cost <= budget:
            out.append({**r, "truncated": False}); used += cost
            continue
        short = len(r["matched_text"]) + len(r["section_heading"])
        if used + short <= budget:
            out.append({**r, "text": r["matched_text"], "truncated": True})
        break
    return out


def detect_game_systems(
    pdf_path: Path,
    text: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> list[str]:
    """Detect all matching TTRPG game systems from folder path or PDF content.

    Detection priority:
    1. Folder name match (user's deliberate organization)
    2. Content keyword match (first 2000 chars of extracted text)
    3. Empty list when nothing matches.

    Both haystack (path/text) and keywords are normalized via
    ``_normalize_for_match`` before substring matching, so case,
    whitespace, punctuation (``&``, ``-``, ``_``, ``.``), and accents
    are ignored.

    Returns matches in ``KNOWN_SYSTEMS`` insertion order, deduped. Path
    matches take precedence over content matches: a path hit blocks the
    content scan from contributing the same tag a second time, but a tag
    that only appears in content is still included.

    Args:
        known_systems: Optional tag→keywords dict. When None, uses the
            module-level KNOWN_SYSTEMS (built-in only). Pass a merged dict
            to include user-defined custom systems in detection.
    """
    systems = known_systems if known_systems is not None else KNOWN_SYSTEMS
    hits: list[str] = []
    seen: set[str] = set()

    path_norm = _normalize_for_match(str(pdf_path))
    for system, keywords in systems.items():
        if any(_normalize_for_match(k) in path_norm for k in keywords if k):
            if system not in seen:
                hits.append(system)
                seen.add(system)

    if text:
        text_norm = _normalize_for_match(text[:2000])
        for system, keywords in systems.items():
            if system in seen:
                continue
            if any(_normalize_for_match(k) in text_norm for k in keywords if k):
                hits.append(system)
                seen.add(system)

    return hits


def detect_game_system(
    pdf_path: Path,
    text: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> str:
    """Detect the primary TTRPG game system (first match) or ``"unknown"``."""
    hits = detect_game_systems(pdf_path, text, known_systems)
    return hits[0] if hits else "unknown"


def detect_systems_in_query(
    query: str,
    known_systems: dict[str, list[str]] | None = None,
) -> set[str]:
    """Game systems named in the query text ("Fireball damage in 5E SRD").

    Same normalized-substring matching as ``detect_game_systems`` uses
    for paths, so keyword hygiene (no ≤3-char keywords) carries over.
    """
    systems = known_systems if known_systems is not None else KNOWN_SYSTEMS
    query_norm = _normalize_for_match(query)
    return {
        tag for tag, keywords in systems.items()
        if any(_normalize_for_match(k) in query_norm for k in keywords if k)
    }


def strip_system_cues(
    query: str,
    known_systems: dict[str, list[str]] | None = None,
) -> str:
    """The query without the game systems it names, for the text that is
    embedded, BM25-matched and reranked ("dragonbane fireball damage" →
    "fireball damage").

    A named system is a scope cue — the boost acts on it — not part of
    what is asked; left in, its words pull toward their meaning
    ("dragonbane" ranks the DRAGON monster first). Only whole words that
    normalize to a keyword are removed: ``detect_systems_in_query``
    matches substrings, which can straddle words, and such a cue still
    boosts but stays in the text. Returns the query unchanged when no cue
    is found or nothing else would be left.
    """
    systems = known_systems if known_systems is not None else KNOWN_SYSTEMS
    needles = {
        n for keywords in systems.values() for k in keywords
        if (n := _normalize_for_match(k))
    }
    if not needles:
        return query
    longest = max(map(len, needles))
    words = query.split()
    norms = [
        _normalize_for_match(w.removesuffix("'s").removesuffix("’s"))
        for w in words
    ]
    drop: set[int] = set()
    for i in range(len(words)):
        joined = ""
        for j in range(i, len(words)):
            joined += norms[j]
            if len(joined) > longest:
                break
            if joined in needles:
                drop.update(range(i, j + 1))
    kept = [w for i, w in enumerate(words) if i not in drop]
    if not drop or not any(norms[i] for i in range(len(words)) if i not in drop):
        return query
    return " ".join(kept)


def _system_matches(
    metadatas: list[dict],
    target_systems: set[str],
    data_dir: Path | None,
    known_systems: dict[str, list[str]],
    manifest: "IndexManifest | None" = None,
) -> list[bool]:
    """Per-candidate: does its source belong to a system the query names?

    A candidate's systems are resolved query-side: the chunk's metadata
    tag, plus the manifest tags for its source (which carry user
    overrides and secondary systems), falling back to keyword detection
    on the source path. The fallback is what makes the boost work
    without a re-index on libraries whose chunks were stamped "unknown"
    before a KNOWN_SYSTEMS keyword existed.

    ``manifest`` is the caller's already-loaded manifest (the search path
    reads it once per request); loading it here is the fallback.
    """
    if manifest is None:
        manifest = load_manifest(data_dir) if data_dir else IndexManifest()
    manifest_files = manifest.files
    by_source: dict[str, bool] = {}
    flags: list[bool] = []
    for meta in metadatas:
        src = meta.get("source", "")
        if src not in by_source:
            systems: set[str] = set()
            tag = meta.get("game_system")
            if tag and tag != "unknown":
                systems.add(tag)
            entry = manifest_files.get(src)
            if entry:
                systems.update(
                    t for t in (entry.game_system, *entry.game_systems)
                    if t and t != "unknown"
                )
            if not systems:
                systems = set(detect_game_systems(Path(src), None, known_systems))
            by_source[src] = bool(systems & target_systems)
        flags.append(by_source[src])
    return flags


def _front_first(flags: list[bool]) -> list[int]:
    """Indexes with flagged ones first, order kept within each group."""
    return sorted(range(len(flags)), key=lambda i: not flags[i])


_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _flatten_br_packed_cells(md: str) -> str:
    """Expand <br>-packed table rows into separate rows.

    pymupdf4llm preserves visually-stacked cells (common in stat blocks:
    "Armor Class:" / "Hit Dice:" sharing a label column) by joining rows
    with <br> inside a single Markdown cell. When the <br> counts in two
    or more cells of a row match, split the row into one row per pair.
    Rows with mismatched counts are legitimate multi-line content and
    pass through unchanged so we never lose data.
    """
    out = []
    for line in md.split("\n"):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2):
            out.append(line)
            continue
        # Strip exactly one leading and trailing "|" so empty edge cells survive.
        cells = [c.strip() for c in stripped[1:-1].split("|")]
        counts = [len(_BR_RE.findall(c)) for c in cells]
        non_zero = [n for n in counts if n > 0]
        if len(non_zero) >= 2 and len(set(non_zero)) == 1:
            n = non_zero[0]
            parts = [_BR_RE.split(c) if cnt else [c] * (n + 1)
                     for c, cnt in zip(cells, counts)]
            for row in zip(*parts):
                out.append("|" + "|".join(p.strip() for p in row) + "|")
        else:
            out.append(line)
    return "\n".join(out)


def _extract_spans(page: pymupdf.Page) -> list[dict]:
    """Per-page font-span side-channel for heading-hierarchy promotion.

    pymupdf flag bits used: 16 = bold, 2 = italic. Sizes rounded to
    2 decimals (matches the spike's signature granularity).
    """
    raw = page.get_text("dict")
    spans: list[dict] = []
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                flags = int(span.get("flags", 0))
                spans.append({
                    "text": text,
                    "size": round(float(span.get("size", 0.0)), 2),
                    "bold": bool(flags & 16),
                    "italic": bool(flags & 2),
                })
    return spans


def _extract_toc(doc: pymupdf.Document) -> dict:
    """Document outline (bookmark tree) for TOC-based heading promotion.

    Returns ``{"n_entries", "max_depth", "entries"}`` where ``entries``
    is ``[[level, title, page1], ...]`` per ``Document.get_toc(simple=True)``.
    Empty entries=[] when the PDF has no outline; promotion falls back
    to font_cluster cleanly in that case.
    """
    toc = doc.get_toc(simple=True)
    if not toc:
        return {"n_entries": 0, "max_depth": 0, "entries": []}
    return {
        "n_entries": len(toc),
        "max_depth": max(entry[0] for entry in toc),
        "entries": toc,
    }


def _extract_pdf_pages(pdf_path: Path) -> list[PageMarkdown]:
    """Extract a PDF page-by-page as Markdown via pymupdf4llm.

    Pipeline (issue #157 — heading-hierarchy promotion adoption):
      pymupdf4llm.to_markdown  +  font-span side-channel  +  TOC
        → promote_headings (toc_then_font; TOC capped at depth 1. The
          `outline` strategy exists but is not the default: it failed its
          validation — docs/retrieval/2026-09-27-outline-headings-design.md)
        → R1 (rejoin CR fragments)
        → R3 (strip image-placeholder chrome)
        → R4 (strip running-heading chrome — cross-page detection)
        → R2 (strip running paragraph headers/footers — cross-page)
        → _flatten_br_packed_cells (atomic-table preservation for the
          structure-aware chunker)

    pymupdf (opened via `fitz`/`pymupdf.open`) also accepts
    .txt/.epub/.xps/.cbz silently; restrict to PDFs to match the
    documented API surface.

    OCR is disabled (`use_ocr=False`): pymupdf4llm otherwise runs Tesseract
    on any page whose text layer it deems unreliable, which dominates
    extraction time on large PDFs. TTRPG rulebooks are overwhelmingly
    digital-native, so the cost rarely buys anything. Scanned or
    OCR-needing PDFs will index with empty/sparse text on those pages.
    """
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF: {pdf_path.name}")
    raw_pages: list[tuple[int, str]] = []
    spans_pages: list[dict] = []
    with pymupdf.open(pdf_path) as doc:
        toc = _extract_toc(doc)
        for i in range(doc.page_count):
            md = pymupdf4llm.to_markdown(doc, pages=[i], show_progress=False, use_ocr=False)
            if md:
                page_no = i + 1
                raw_pages.append((page_no, md))
                spans_pages.append({
                    "page_number": page_no,
                    "spans": _extract_spans(doc.load_page(i)),
                })
    if not raw_pages:
        return []
    pages_dict = [{"page_number": pn, "markdown": md} for pn, md in raw_pages]
    promoted, promo_report = promote_markdown(
        pages_dict, spans_pages, toc, strategy="toc_then_font"
    )
    print(
        f"[promote] {pdf_path.name}: "
        f"strategy={promo_report['strategy']} "
        f"n_headings={promo_report['n_headings']} "
        f"toc_used={promo_report['toc_used']} "
        f"font_used={promo_report['font_used']} "
        f"fallback={promo_report['fallback_count']} "
        f"distribution={promo_report['promoted_level_distribution']} "
        f"junk={promo_report.get('junk_demoted', 0)} "
        f"toc_depth={promo_report.get('toc_effective_depth', 1)}"
        + (
            f" outline={'trusted' if promo_report['outline_trusted'] else 'fallback'}"
            f" entries={promo_report['outline_entries']}"
            f" placed={promo_report['outline_placed']}"
            f" (existing={promo_report['outline_existing']}"
            f" promoted={promo_report['outline_promoted']}"
            f" unplaced={promo_report['outline_unplaced']})"
            f" boxes={promo_report['outline_boxes']}"
            f" span={promo_report['outline_span']}"
            if "outline_trusted" in promo_report else ""
        )
    )
    cleaned, report = clean_pages([p["markdown"] for p in promoted])
    print(f"[cleanup] {pdf_path.name}: {report.summary()}")
    return [
        PageMarkdown(page_number=pn, markdown=_flatten_br_packed_cells(md))
        for (pn, _), md in zip(raw_pages, cleaned)
    ]


def _page_labels(pdf_path: Path) -> dict[int, str]:
    """Map 1-based physical page numbers to the label printed on the page.

    TTRPG PDFs carry covers, front matter and ads, so physical page 312 is
    routinely printed as 276 — and a page number a GM cannot find at the table
    is not a useful citation. Entries whose label already equals the physical
    number carry no information and are omitted; consumers fall back to
    page_start.
    """
    labels: dict[int, str] = {}
    with pymupdf.open(pdf_path) as doc:
        for i in range(doc.page_count):
            label = (doc.load_page(i).get_label() or "").strip()
            if label and label != str(i + 1):
                labels[i + 1] = label
    return labels


def _extract_pdf_text(pdf_path: Path) -> str:
    """Flat-string view of the PDF — used by game-system detection."""
    return "\n\n".join(p.markdown for p in _extract_pdf_pages(pdf_path))


def path_key(path: PurePath) -> str:
    """A tree path as the UI, manifest and store spell it: '/' separators
    on every platform. The UI receives '/'-spelled paths from the Tauri
    shell and splits on '/'; a Windows Path prints with '\\', so a path
    rebuilt from a Path is re-spelled here before it becomes a key."""
    return path.as_posix()


def file_content_hash(path: Path) -> str:
    """Compute SHA-256 hash of file contents. Reads in 64KB chunks for memory efficiency."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class IndexFilesRequest(BaseModel):
    paths: list[str]
    game_system: str | None = None

class ReindexFileRequest(BaseModel):
    path: str
    game_system: str | None = None

class IndexStatusRequest(BaseModel):
    selected_paths: list[str]

class SyncIndexRequest(BaseModel):
    selected_paths: list[str]
    game_system_overrides: dict[str, str] | None = None
    force: bool = False

class SearchRequest(BaseModel):
    query: str
    n_results: int = Field(15, ge=1)
    source_filter: str | None = None
    game_system: str | None = None
    game_systems: list[str] | None = None
    collection: str | None = None
    source_paths: list[str] | None = None
    # Pipeline knobs. ``None`` means "use the persisted search settings"
    # (search_settings.json in the data dir; see SearchSettings below) —
    # resolution order is request field > persisted setting > built-in
    # default. The desktop UI and MCP omit these, so the settings modal
    # governs both; the eval harness passes them explicitly so it stays
    # pinned to the configuration it claims to measure.
    #
    # rerank: cross-encoder rerank of the candidate pool. Default on. The
    # 2026-07-10 eval ablation favored rerank-off (nDCG@10 0.727 vs
    # 0.655, 7x faster — evals/baselines/2026-07-10-rerank-off-p25.md),
    # and the default was briefly flipped, but real-library search
    # quality regressed visibly and the flip was reverted same day: the
    # 3-book eval corpus underrepresents the many-similar-candidates
    # regime of a real library, which is where cross-encoders earn
    # their cost. Treat the harness as necessary-not-sufficient for
    # rerank decisions until the corpus grows.
    rerank: bool | None = None
    # rerank_candidates: cross-encoder pool size (clamped to
    # RERANK_POOL_MIN..RERANK_POOL_MAX). Built-in default is
    # RERANK_CANDIDATE_POOL (env RERANK_CANDIDATES, 50).
    rerank_candidates: int | None = None
    # hybrid: BM25 over the same chunks joins the dense ranking — the
    # BM25 top-M enters the rerank pool (roadmap 3.1). Default on since
    # 2026-09-23 (`2026-09-23-v2-hybrid`: keyword MRR@5 0.882 → 0.912,
    # cued 0.729 → 0.771, no query worse).
    hybrid: bool | None = None
    # lex_weight: RRF weight of the BM25 ranking under `hybrid` (dense
    # rankings weigh 1.0). Request-only eval knob, not a persisted
    # setting; None means LEXICAL_RRF_WEIGHT.
    lex_weight: float | None = Field(default=None, ge=0)
    # lex_pool: BM25 top-M added to the dense top-N in the hybrid rerank
    # pool. Request-only eval knob; None means LEXICAL_RERANK_POOL.
    lex_pool: int | None = Field(default=None, ge=0)
    # spell_correction: rewrite out-of-vocabulary query tokens to the
    # closest library term before embedding (typo-tolerance design,
    # section A). Default on — the 2026-07-10 eval gate passed once
    # general-English words were protected from rewriting: clean queries
    # reproduce the no-correction baseline to the digit, and the typo set
    # closes >half its nDCG/MRR gap
    # (evals/baselines/2026-07-10-spellfix-en-guard.md).
    spell_correction: bool | None = None
    # variant_expansion: search spacing variants of the query
    # ("chainmail" ↔ "chain mail") alongside it and fuse via RRF
    # (typo-tolerance design, section B). Default off — the 2026-07-10
    # eval gate failed: spacing variants gained nothing (bge-m3 subwords
    # already absorb spacing) and clean queries regressed
    # (evals/baselines/2026-07-10-variant-expansion.md).
    variant_expansion: bool | None = None
    # partial: the query's last word may still be being typed. The app
    # searches as the GM types (300 ms debounce) and sends this for a
    # debounced search whose text does not end in whitespace; Enter
    # commits with it off. The trailing word is then never spell-
    # corrected ("grapp" would become "grasp") and BM25 matches it as a
    # prefix. Request-only, not a setting.
    partial: bool = False
    # strip_cues: a game system named in the query boosts that system's
    # books but is left out of the text that is embedded, BM25-matched and
    # reranked (roadmap 2026-09-26 item 4). Request-only eval knob.
    strip_cues: bool = True
    # max_context_chars: cap the total `len(text) + len(section_heading)`
    # across returned results (roadmap 2.2). None (default) is unlimited;
    # otherwise results are packed in rank order and the first one that
    # doesn't fit is cut to its matched unit — see `pack_results`.
    max_context_chars: int | None = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Search settings — user-tunable pipeline knobs, persisted in the data dir
# (docs/retrieval/2026-07-11-search-settings-design.md). These are the
# sidecar-wide defaults: every caller (desktop UI, MCP) inherits them unless
# the request sets the corresponding SearchRequest field.
# ---------------------------------------------------------------------------

SEARCH_SETTINGS_FILENAME = "search_settings.json"
# v2 (2026-09-23): hybrid became default-on. v1 files wrote every field,
# so their `hybrid: false` is the old default, not a choice — it is
# dropped on load. Files without a version are v1.
SEARCH_SETTINGS_VERSION = 2


class SearchSettings(BaseModel):
    rerank: bool = True
    rerank_candidates: int = RERANK_CANDIDATE_POOL
    spell_correction: bool = True
    hybrid: bool = True
    variant_expansion: bool = False

    @field_validator("rerank_candidates")
    @classmethod
    def _clamp_pool(cls, v: int) -> int:
        return max(RERANK_POOL_MIN, min(RERANK_POOL_MAX, v))


class SearchSettingsUpdate(BaseModel):
    """Partial update for PUT /api/search-settings — None fields untouched."""
    rerank: bool | None = None
    rerank_candidates: int | None = None
    spell_correction: bool | None = None
    hybrid: bool | None = None
    variant_expansion: bool | None = None


def load_search_settings(data_dir: Path) -> SearchSettings:
    """Load persisted settings; missing file, unknown keys, or a corrupt
    file all resolve to defaults — search must keep working regardless."""
    path = data_dir / SEARCH_SETTINGS_FILENAME
    if not path.exists():
        return SearchSettings()
    try:
        raw = json.loads(path.read_text())
        if raw.get("version", 1) < 2:
            raw.pop("hybrid", None)
        known = {k: raw[k] for k in SearchSettings.model_fields if k in raw}
        return SearchSettings(**known)
    except Exception as e:
        print(f"Unreadable {SEARCH_SETTINGS_FILENAME} ({e}); using default search settings")
        return SearchSettings()


def save_search_settings(data_dir: Path, settings: SearchSettings) -> None:
    """Write search settings to disk atomically."""
    path = data_dir / SEARCH_SETTINGS_FILENAME
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(
        {**settings.model_dump(), "version": SEARCH_SETTINGS_VERSION},
        indent=2,
    ))
    os.replace(tmp_path, path)


def resolve_search_knobs(
    request: SearchRequest,
    data_dir: Path | None,
    settings: SearchSettings | None = None,
) -> SearchSettings:
    """Effective knobs for one search: request field > persisted > default.

    Returns a validated SearchSettings (pool size clamped), so the search
    handler reads every knob from one object regardless of its origin.
    ``settings`` is the caller's already-loaded persisted settings (the
    search path reads them once per request); loading them is the fallback.
    """
    if settings is not None:
        base = settings
    else:
        base = load_search_settings(data_dir) if data_dir else SearchSettings()
    overrides = {
        k: getattr(request, k)
        for k in SearchSettings.model_fields
        if getattr(request, k) is not None
    }
    if not overrides:
        return base
    return SearchSettings(**{**base.model_dump(), **overrides})


class SetGameSystemsRequest(BaseModel):
    # ``path`` addresses one file; ``filename`` is the legacy form and is
    # refused when two indexed files share it (#330).
    filename: str | None = None
    path: str | None = None
    game_systems: list[str]

class CustomGameSystemRequest(BaseModel):
    tag: str
    keywords: list[str] = []
    color: str | None = None

class ToggleBuiltinRequest(BaseModel):
    tag: str
    disabled: bool

class CreateCollectionRequest(BaseModel):
    name: str
    file_paths: list[str]
    description: str = ""
    color: str | None = None

class UpdateCollectionRequest(BaseModel):
    file_paths: list[str] | None = None
    description: str | None = None
    color: str | None = None
    archived: bool | None = None
    last_used_at: str | None = None

class RenameCollectionRequest(BaseModel):
    new_name: str


# ---------------------------------------------------------------------------
# Index manifest — tracks what's been indexed and when
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "index_manifest.json"


class ManifestEntry(BaseModel):
    filename: str
    mtime: float
    chunk_count: int
    indexed_at: str
    game_system: str = "unknown"
    game_systems: list[str] = []
    content_hash: str = ""
    file_size: int = 0
    pipeline_version: str = ""
    # Set when the most recent re-index attempt failed. The previous
    # successful index (chunk_count, indexed_at, content_hash, ...) is
    # preserved so search keeps working until the next sync retries.
    last_error: str | None = None
    last_error_at: str | None = None

    def model_post_init(self, __context):
        # Backfill on load for entries written before multi-tag support.
        if not self.game_systems and self.game_system != "unknown":
            self.game_systems = [self.game_system]


class IndexManifest(BaseModel):
    version: int = 1
    files: dict[str, ManifestEntry] = {}


def _load_json_store(path: Path, parse):
    """``parse`` the JSON at ``path``; None when the file is missing.

    An unreadable or wrongly-shaped file is renamed to
    ``<name>.corrupt-<timestamp>`` and treated as missing. The stores are
    written atomically, so this is a hand edit or disk damage; moving it
    aside keeps the sidecar booting without letting the next save
    overwrite what the user may want to repair.
    """
    if not path.exists():
        return None
    try:
        return parse(json.loads(path.read_text()))
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        aside = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}")
        os.replace(path, aside)
        print(f"Unreadable {path.name} ({e}); moved to {aside.name}, starting empty")
        return None


def load_manifest(data_dir: Path) -> IndexManifest:
    """Load the index manifest from disk, or return an empty one."""
    manifest = _load_json_store(data_dir / MANIFEST_FILENAME, lambda raw: IndexManifest(**raw))
    return manifest if manifest is not None else IndexManifest()


def manifest_digest(manifest: IndexManifest) -> str:
    """Content fingerprint of an index: what is indexed, at what version.

    Sorted ``(path, content_hash, pipeline_version)`` triples, hashed. It
    moves whenever a file is added, removed, re-indexed with different
    content, or re-run through a different pipeline — and not when an
    unrelated field (mtime, last_error, a game-system retag) is rewritten.
    Caches derived from the indexed text key on it.
    """
    payload = "\n".join(
        f"{path}\t{entry.content_hash}\t{entry.pipeline_version}"
        for path, entry in sorted(manifest.files.items())
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def save_manifest(data_dir: Path, manifest: IndexManifest) -> None:
    """Write the index manifest to disk atomically."""
    manifest_path = data_dir / MANIFEST_FILENAME
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(manifest.model_dump_json(indent=2))
    os.replace(tmp_path, manifest_path)


def _mark_manifest_error(
    manifest: IndexManifest,
    data_dir: Path | None,
    path_str: str,
    error: str,
) -> None:
    """Record a re-index failure on the existing manifest entry, if any.

    No-op when the entry doesn't exist (e.g. a brand-new add that failed —
    nothing to preserve, just retry on next sync). Persists the manifest.
    """
    if not data_dir:
        return
    entry = manifest.files.get(path_str)
    if entry is None:
        return
    entry.last_error = error
    entry.last_error_at = datetime.now(timezone.utc).isoformat()
    save_manifest(data_dir, manifest)


# ---------------------------------------------------------------------------
# Collections — named subsets of indexed files
# ---------------------------------------------------------------------------

COLLECTIONS_FILENAME = "collections.json"
COLLECTIONS_STORE_VERSION = 2


class Collection(BaseModel):
    id: str
    name: str
    file_paths: list[str]
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    description: str = ""
    color: str | None = None
    archived: bool = False


class CollectionsStore(BaseModel):
    version: int = COLLECTIONS_STORE_VERSION
    collections: dict[str, Collection] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Collections store their pigment's hex, so a palette change remaps here.
# Retired pigments → their successors in the current sorcerer's cabinet
# (src/lib/legend-lore/palette.ts). The cabinet keeps one green: every
# retired green folds into Malachite.
_RETIRED_PIGMENTS = {
    # Manuscript pigments
    "#c2736d": "#eb98a2",  # Madder    → Madder
    "#bb7b4e": "#f29349",  # Ember     → Realgar
    "#9f8b3e": "#e6c667",  # Gilt      → Ochre
    "#6b9b60": "#66965c",  # Moss      → Malachite
    "#2fa094": "#66965c",  # Verdigris → Malachite
    "#5b90c7": "#478bdb",  # Woad      → Lapis
    "#b5739f": "#d379b7",  # Plum      → Murex
    # First cabinet
    "#d07c87": "#eb98a2",  # Madder    → Madder
    "#abc279": "#e6c667",  # Arsenic   → Ochre
    "#4e9766": "#66965c",  # Malachite → Malachite
    "#43a49f": "#66965c",  # Verdigris → Malachite
    "#6b9ad0": "#478bdb",  # Woad      → Lapis
    "#dba2c3": "#d379b7",  # Murex     → Murex
}


def _migrate_collection_record(name: str, raw: dict) -> dict:
    """Fill in v2 fields for an on-disk record. v1 records get sensible defaults.

    Colors from the retired pigment palette load as their successors.
    """
    created_at = raw.get("created_at") or _now_iso()
    color = raw.get("color")
    return {
        "id": raw.get("id") or str(uuid.uuid4()),
        "name": raw.get("name") or name,
        "file_paths": raw.get("file_paths", []),
        "created_at": created_at,
        "updated_at": raw.get("updated_at") or created_at,
        "last_used_at": raw.get("last_used_at"),
        "description": raw.get("description", ""),
        "color": _RETIRED_PIGMENTS.get(color, color),
        "archived": raw.get("archived", False),
    }


def load_collections(data_dir: Path) -> CollectionsStore:
    """Load collections from disk, migrating legacy records to the current schema."""
    def parse(raw):
        migrated = {
            name: _migrate_collection_record(name, c)
            for name, c in raw.get("collections", {}).items()
        }
        return CollectionsStore(
            version=COLLECTIONS_STORE_VERSION,
            collections=migrated,
        )

    store = _load_json_store(data_dir / COLLECTIONS_FILENAME, parse)
    return store if store is not None else CollectionsStore()


def save_collections(data_dir: Path, store: CollectionsStore) -> None:
    """Write collections to disk atomically."""
    path = data_dir / COLLECTIONS_FILENAME
    tmp_path = path.with_suffix(".json.tmp")
    store.version = COLLECTIONS_STORE_VERSION
    tmp_path.write_text(store.model_dump_json(indent=2))
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Custom game systems — user-defined systems that merge with built-ins
# ---------------------------------------------------------------------------

CUSTOM_SYSTEMS_FILENAME = "custom_game_systems.json"


class CustomGameSystemEntry(BaseModel):
    tag: str
    keywords: list[str] = []
    color: str | None = None


class CustomGameSystemsStore(BaseModel):
    version: int = 1
    systems: list[CustomGameSystemEntry] = []
    disabled_builtins: list[str] = []


def load_custom_systems(data_dir: Path) -> CustomGameSystemsStore:
    """Load custom game systems from disk, or return an empty store."""
    store = _load_json_store(
        data_dir / CUSTOM_SYSTEMS_FILENAME, lambda raw: CustomGameSystemsStore(**raw)
    )
    return store if store is not None else CustomGameSystemsStore()


def save_custom_systems(data_dir: Path, store: CustomGameSystemsStore) -> None:
    """Write custom game systems to disk atomically."""
    path = data_dir / CUSTOM_SYSTEMS_FILENAME
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(store.model_dump_json(indent=2))
    os.replace(tmp_path, path)


def get_merged_systems(
    custom_store: CustomGameSystemsStore,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Merge built-in GAME_SYSTEMS with custom overrides/additions.

    Returns (merged_list, known_systems_dict) where:
    - merged_list: full entries with tag, keywords, color, is_builtin,
      is_customized. ``color`` is ``None`` when the user opted out;
      built-in overrides without a custom color inherit the built-in's
      default. The frontend renders a neutral fallback for ``None``.
    - known_systems_dict: tag → keywords mapping for detect_game_system
    """
    builtin_by_tag = {entry["tag"]: entry for entry in GAME_SYSTEMS}
    custom_tags = {entry.tag for entry in custom_store.systems}
    disabled = set(custom_store.disabled_builtins)

    merged = []
    for entry in GAME_SYSTEMS:
        if entry["tag"] in disabled:
            continue
        if entry["tag"] in custom_tags:
            # Custom entry overrides built-in with same tag
            continue
        merged.append({**entry, "is_builtin": True, "is_customized": False})

    for entry in custom_store.systems:
        is_override = entry.tag in builtin_by_tag
        # Override inherits the built-in color when the user didn't pick one;
        # pure-custom entries with no color stay None so the UI can render
        # an explicit "no color" state.
        if entry.color is not None:
            color = entry.color
        elif is_override:
            color = builtin_by_tag[entry.tag].get("color")
        else:
            color = None
        merged.append({
            "tag": entry.tag,
            "keywords": entry.keywords,
            "color": color,
            "is_builtin": is_override,
            "is_customized": is_override,
        })

    known = {e["tag"]: e["keywords"] for e in merged}
    return merged, known


def resolve_collection_paths(
    coll: Collection, manifest: IndexManifest
) -> list[str]:
    """Resolve a collection's file_paths to the indexed subset.

    Filters out paths no longer indexed (graceful degradation). Returns
    exact source paths — books are keyed by full path, and filtering by
    bare filename would leak same-named PDFs from other folders into the
    collection scope (issue #308; the '/5e/Monster Manual.pdf' vs
    '/pf2e/Monster Manual.pdf' case).
    """
    return [p for p in coll.file_paths if p in manifest.files]


# ---------------------------------------------------------------------------
# Reusable indexing / deletion helpers
# ---------------------------------------------------------------------------


def warm_search_stack(get_spell_corrector, report=lambda step, state: None) -> None:
    """Pay search's lazy loads at boot rather than in the first query.

    Two things in the search path build themselves on first use: the
    cross-encoder (a ~120 MB ONNX model, seconds to load) and the
    spell-correction vocabulary. Whoever searches first after a start
    pays both — the keep-warm ticker only covers Ollama. Issue #341.

    Diagnostics-grade error handling, like ``keep_embedder_warm``: a
    warm-up that fails must never take the sidecar down at boot, and the
    next real search reports the problem with far better context.

    ``report(step, state)`` feeds the splash window's lamps (``/api/boot``):
    each step goes ``running`` before its load and ``done`` or ``failed``
    after it; a disabled reranker is ``skipped``.
    """
    if os.getenv("RERANK_DISABLED") == "1":
        report("reranker", "skipped")
    else:
        report("reranker", "running")
        try:
            # None is the reranker's fallback signal: the model didn't load.
            if rerank_scores("warm", ["warm"]) is None:
                report("reranker", "failed")
            else:
                report("reranker", "done")
        except Exception:
            report("reranker", "failed")
    report("spelling", "running")
    try:
        get_spell_corrector()
        report("spelling", "done")
    except Exception:
        report("spelling", "failed")


# How much of the heading path each ranking input carries: "path" (the
# whole breadcrumb, production), "leaf" (its last segment) or "none".
# Eval-only switches for the heading ablation (roadmap 2026-09-26 item 3):
# embeddings and BM25 are fixed at index time, so an index built under one
# setting must be searched under the same one.
HEADING_EMBED = os.getenv("HEADING_EMBED", "path")
HEADING_FTS = os.getenv("HEADING_FTS", "path")
HEADING_RERANK = os.getenv("HEADING_RERANK", "path")


def _with_heading(heading: str | None, text: str, mode: str) -> str:
    if not heading or mode == "none":
        return text
    if mode == "leaf":
        heading = heading.rsplit(" > ", 1)[-1]
    return f"{heading}\n\n{text}"


def _embed_text(eu: EmbedUnit) -> str:
    """Heading-prepended text for embedding (storage of eu.text unchanged).

    hybrid_retrieval_spike measured +0.184 MRR@5 / +0.150 recall@5 from this
    one change: embedding sees the section_heading breadcrumb as topical
    context for the embed unit body.
    """
    return _with_heading(eu.section_heading, eu.text, HEADING_EMBED)


def _fts_text(eu: EmbedUnit) -> str:
    """The unit's BM25 text — also the spell vocabulary's source."""
    return _with_heading(eu.section_heading, eu.text, HEADING_FTS)


# Embed batching tunables (issue #158).
# 256 was chosen over the previous 100 to amortize Ollama per-call overhead;
# bge-m3 embeds each input independently so the 8192 ctx applies per input,
# not per batch (mean embed-text size ~400 chars / ~100 tokens). Concurrency=3
# fires up to N embed batches at Ollama in parallel; the book is written to
# the store once, after every batch has embedded.
EMBED_BATCH_SIZE = 256
EMBED_CONCURRENCY = 3


# A model runner can drop an in-flight embed ("connection reset by peer")
# under a large book's sustained embed load — OSRIC (46 batches) hit this
# reliably where smaller books never did. Without a retry, one transient
# reset raises EmbedBatchError and aborts the *whole* file's index. Retry
# ONLY transient connection failures; a deterministic error (bad input,
# wedged model) won't be fixed by retrying and must surface immediately.
EMBED_MAX_ATTEMPTS = 3

_TRANSIENT_EMBED_MARKERS = (
    "connection reset", "reset by peer", "connection refused",
    "connection aborted", "broken pipe", "timed out", "timeout",
    "temporarily unavailable", "eof",
)


def _is_transient_embed_error(exc: Exception) -> bool:
    """A dropped/failed connection worth retrying, vs a deterministic error
    a retry can't fix."""
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    msg = str(exc).lower()
    return any(m in msg for m in _TRANSIENT_EMBED_MARKERS)


def _embed_batch(embed_fn, batch: list[EmbedUnit]) -> list[list[float]]:
    """Heading-prepended embeddings for a batch (no DB writes).

    Retries transient Ollama runner resets so a single dropped connection
    mid-index does not abort the entire file; non-transient failures raise
    immediately.
    """
    texts = [_embed_text(eu) for eu in batch]
    for attempt in range(1, EMBED_MAX_ATTEMPTS + 1):
        try:
            return embed_fn(texts)
        except Exception as e:
            if attempt == EMBED_MAX_ATTEMPTS or not _is_transient_embed_error(e):
                raise
            print(f"embed batch failed (attempt {attempt}/{EMBED_MAX_ATTEMPTS}, "
                  f"transient): {str(e)[:120]} — retrying", flush=True)
            time.sleep(1.0 * attempt)


class EmbedBatchError(Exception):
    """Raised when embedding fails for a single source.

    Carries the source path so callers can record which file failed and
    preserve any prior successful index for it. The original cause is
    chained via ``__cause__``.
    """

    def __init__(self, source_path: Path, message: str):
        super().__init__(f"{source_path.name}: {message}")
        self.source_path = source_path


def _embed_units(
    embed_fn,
    embed_units: list[EmbedUnit],
    pdf_path: Path,
    vectors: list[list[float]],
    batch_size: int = EMBED_BATCH_SIZE,
    concurrency: int = EMBED_CONCURRENCY,
):
    """Embed batches concurrently, collecting vectors in submission order.

    Generator that appends each batch's vectors to ``vectors`` and yields
    its unit count, so streaming callers can report progress while the
    book is still embedding. Submission-order draining keeps ``vectors``
    aligned with ``embed_units``.

    Raises ``EmbedBatchError`` if any batch fails. Pending futures are
    cancelled before the exception propagates so the executor exits
    promptly.
    """
    if not embed_units:
        return
    batches = [
        embed_units[i:i + batch_size]
        for i in range(0, len(embed_units), batch_size)
    ]
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(_embed_batch, embed_fn, b) for b in batches]
        try:
            for batch, fut in zip(batches, futures):
                vectors.extend(fut.result())
                yield len(batch)
        except Exception as e:
            for f in futures:
                f.cancel()
            raise EmbedBatchError(pdf_path, str(e)) from e


def _atomic_index_pdf(
    pdf_path: Path,
    game_system: str,
    game_systems: list[str],
    embed_units: list[EmbedUnit],
    parents: list,
    store: LibraryStore,
    embed_fn,
    batch_size: int = EMBED_BATCH_SIZE,
    page_labels: dict[int, str] | None = None,
):
    """Generator: embed a book, then swap it into the store in one transaction.

    Yields each batch's unit count as it embeds so callers can surface
    progress. Nothing is written until every batch has embedded; then
    ``replace_document`` replaces the book's units, vectors, FTS rows and
    parents together. On ``EmbedBatchError`` the store is untouched, so a
    previous index of the book keeps serving searches.
    """
    vectors: list[list[float]] = []
    yield from _embed_units(
        embed_fn, embed_units, pdf_path, vectors, batch_size=batch_size,
    )
    store.replace_document(
        path_key(pdf_path), game_system, game_systems, embed_units,
        embed_texts=[_fts_text(eu) for eu in embed_units],
        vectors=vectors, parents=parents, page_labels=page_labels,
    )


def _index_chunks(
    chunks: list[Chunk],
    pdf_path: Path,
    game_system: str,
    game_systems: list[str],
    store: LibraryStore,
    embed_fn,
    batch_size: int = EMBED_BATCH_SIZE,
) -> int:
    """Run the granularity step and persist embed units + parents.

    Splits chunks into ~400-char embed units (tables linearized into row
    units, atomic fallback) and contiguous same-breadcrumb parents (capped
    at 6,000 chars), embeds the units and writes the book in one store
    transaction. Raises ``EmbedBatchError`` if embedding fails — the
    book's previous index stays intact in that case.

    Returns the number of embed units written.
    """
    if not chunks:
        return 0
    embed_units, parents = build_granularity(chunks)
    return sum(_atomic_index_pdf(
        pdf_path, game_system, game_systems, embed_units, parents, store,
        embed_fn, batch_size=batch_size, page_labels=_page_labels(pdf_path),
    ))


def _extract_and_chunk(
    pdf_path: Path, game_system: str | None,
    known_systems: dict[str, list[str]] | None,
) -> tuple[list[Chunk], str, list[str], str | None]:
    """Shared preamble: extract pages, detect system, run structure_aware.

    Returns (chunks, resolved_system, resolved_systems, error_message).
    ``resolved_system`` is the primary tag (first match) stored in chunk
    metadata; ``resolved_systems`` is the full multi-tag list stored in
    the manifest. When ``game_system`` is provided as an override, the
    list contains just that single tag.
    """
    if not pdf_path.exists():
        return [], "unknown", [], f"{pdf_path.name}: File not found"
    try:
        pages = _extract_pdf_pages(pdf_path)
        if not pages:
            return [], "unknown", [], f"{pdf_path.name}: Empty or scanned PDF"
        flat_text = "\n\n".join(p.markdown for p in pages)
        if not flat_text.strip():
            return [], "unknown", [], f"{pdf_path.name}: Empty or scanned PDF"
        if game_system:
            resolved_system = game_system
            resolved_systems = [game_system]
        else:
            resolved_systems = detect_game_systems(
                pdf_path, flat_text, known_systems=known_systems
            )
            resolved_system = resolved_systems[0] if resolved_systems else "unknown"
        # Full path, not .name: source_pdf seeds _make_parent_id, and two
        # same-named PDFs in different folders would otherwise generate
        # colliding parent_ids — the second file dies on the parents-store
        # UNIQUE constraint and never indexes (issue #308 family). The
        # parents store itself is already keyed by full path.
        chunks = structure_aware(pages, source_pdf=path_key(pdf_path))
        return chunks, resolved_system, resolved_systems, None
    except Exception as e:
        return [], "unknown", [], f"{pdf_path.name}: {str(e)}"


def index_single_pdf(
    pdf_path: Path, store: LibraryStore, embed_fn,
    game_system: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> tuple[int, str | None, str, list[str]]:
    """Extract, chunk, embed and write a single PDF to the library store.

    Returns (embed_unit_count, error_message, game_system, game_systems).
    error_message is None on success. Embedding failures are converted to
    an error message so callers can surface them without crashing — any
    pre-existing chunks/parents for this source are left intact.
    """
    chunks, resolved_system, resolved_systems, error = _extract_and_chunk(
        pdf_path, game_system, known_systems
    )
    if error:
        return 0, error, resolved_system, resolved_systems
    try:
        count = _index_chunks(
            chunks, pdf_path, resolved_system, resolved_systems, store, embed_fn
        )
    except EmbedBatchError as e:
        return 0, str(e), resolved_system, resolved_systems
    return count, None, resolved_system, resolved_systems


def prepare_pdf(
    pdf_path: Path, game_system: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> tuple[list[Chunk], str, list[str], str | None]:
    """Extract text and chunk a PDF without upserting.

    Returns (chunks, game_system, game_systems, error_message).
    error_message is None on success.
    """
    return _extract_and_chunk(pdf_path, game_system, known_systems)


# UUID-named segment directories created by Chroma's HNSW persistence.
_UUID_DIR_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# What the pre-library-store index left in the data dir.
_LEGACY_STORE_FILES = ("chroma.sqlite3", "parents.sqlite3")


def remove_legacy_chroma(data_dir: Path) -> int:
    """Delete the ChromaDB store and the old parents file. Returns bytes freed.

    The library store replaced both (docs/retrieval/2026-09-26-library-
    store-design.md); the library is rebuilt rather than migrated, and the
    ``PIPELINE_VERSION`` bump flags every manifest entry for reindex. The
    UUID pattern guards against removing unrelated directories. Safe to
    call on every boot: a data dir without legacy files costs a listing.
    """
    import shutil

    freed = 0
    for name in _LEGACY_STORE_FILES:
        for path in data_dir.glob(name + "*"):  # -wal / -shm / -journal too
            freed += path.stat().st_size
            path.unlink()
    for entry in data_dir.iterdir():
        if entry.is_dir() and _UUID_DIR_RE.match(entry.name):
            freed += sum(p.stat().st_size for p in entry.rglob("*") if p.is_file())
            shutil.rmtree(entry, ignore_errors=True)
    return freed


def compute_diff(
    selected_paths: list[str], manifest: IndexManifest
) -> dict[str, list[dict]]:
    """Compare selected paths against the manifest to find what changed.

    Returns a dict with keys: to_add, to_remove, to_rename, to_update,
    up_to_date, errors.  Each value is a list of dicts describing the file.

    Pure diff — does not factor in user intent like "reindex everything."
    Callers wanting to force-reprocess unchanged files should promote
    ``up_to_date`` into ``to_update`` themselves (see ``_sync_core``).
    """
    selected = set(selected_paths)
    indexed = set(manifest.files.keys())

    to_add = []
    to_update = []
    up_to_date = []
    errors = []
    outdated: list[str] = []
    missing_indexed: list[tuple[str, ManifestEntry]] = []

    stale_paths: list[str] = []

    for path_str in selected:
        path = Path(path_str)
        if path_str not in indexed:
            # New file — not yet indexed
            if not path.exists():
                # Stale selection — file never indexed and doesn't exist.
                # Not an error; frontend should drop this path from selections.
                stale_paths.append(path_str)
            else:
                to_add.append({"path": path_str, "filename": path.name})
        else:
            # Already indexed — check if modified
            entry = manifest.files[path_str]
            if not path.exists():
                # Defer — might be a rename; we'll scan the parent dir below
                missing_indexed.append((path_str, entry))
            else:
                current_mtime = os.path.getmtime(path_str)
                if current_mtime != entry.mtime:
                    to_update.append({
                        "path": path_str,
                        "filename": path.name,
                        "chunk_count": entry.chunk_count,
                        "game_system": entry.game_system,
                        "game_systems": list(entry.game_systems),
                        "indexed_at": entry.indexed_at,
                        "pipeline_version": entry.pipeline_version,
                    })
                    if entry.pipeline_version != PIPELINE_VERSION:
                        outdated.append(path_str)
                else:
                    up_to_date.append({
                        "path": path_str,
                        "filename": path.name,
                        "chunk_count": entry.chunk_count,
                        "game_system": entry.game_system,
                        "game_systems": list(entry.game_systems),
                        "indexed_at": entry.indexed_at,
                        "pipeline_version": entry.pipeline_version,
                    })
                    if entry.pipeline_version != PIPELINE_VERSION:
                        outdated.append(path_str)

    # --- Resolve missing indexed files ---
    # For each missing file, check if its parent directory is accessible.
    # If so, scan for a rename candidate (same content hash). If no rename
    # is found, the file was genuinely deleted → auto-remove from index.
    # If the parent is inaccessible (e.g. unmounted drive), keep as error.
    to_remove: list[dict] = []
    to_auto_remove: list[dict] = []
    for path_str, entry in missing_indexed:
        parent = Path(path_str).parent
        if not parent.is_dir():
            # Parent inaccessible — possible unmounted drive, keep as error
            errors.append({"path": path_str, "error": "File not found on disk"})
            continue

        # Try rename detection if we have a content hash
        found_rename = False
        if entry.content_hash:
            try:
                for candidate in parent.iterdir():
                    if candidate.suffix.lower() != ".pdf":
                        continue
                    cand_str = path_key(candidate)
                    if cand_str in selected or cand_str in indexed:
                        continue  # already tracked
                    try:
                        if candidate.stat().st_size != entry.file_size:
                            continue
                    except OSError:
                        continue
                    if file_content_hash(candidate) == entry.content_hash:
                        # Match! Route through rename detection pipeline.
                        to_remove.append({
                            "path": path_str,
                            "filename": entry.filename,
                            "chunk_count": entry.chunk_count,
                            "game_system": entry.game_system,
                            "game_systems": list(entry.game_systems),
                        })
                        to_add.append({"path": cand_str, "filename": candidate.name})
                        found_rename = True
                        break
            except OSError:
                pass

        if not found_rename:
            # Parent accessible, file gone, no rename match → auto-remove
            to_auto_remove.append({
                "path": path_str,
                "filename": entry.filename,
                "chunk_count": entry.chunk_count,
                "game_system": entry.game_system,
                "game_systems": list(entry.game_systems),
            })

    # Files in manifest but no longer selected → to_remove
    to_remove += [
        {
            "path": path_str,
            "filename": manifest.files[path_str].filename,
            "chunk_count": manifest.files[path_str].chunk_count,
            "game_system": manifest.files[path_str].game_system,
            "game_systems": list(manifest.files[path_str].game_systems),
        }
        for path_str in (indexed - selected)
    ]

    # --- Rename detection ---
    # Match to_add files against to_remove files by content hash.
    # Uses file_size as a cheap pre-filter before computing SHA-256.
    to_rename = []
    if to_add and to_remove:
        # Build lookup from content_hash → to_remove entry (only entries with a hash)
        remove_by_hash: dict[str, list[dict]] = {}
        remove_sizes: dict[int, list[str]] = {}
        for entry in to_remove:
            manifest_entry = manifest.files[entry["path"]]
            if manifest_entry.content_hash:
                remove_by_hash.setdefault(manifest_entry.content_hash, []).append(entry)
            if manifest_entry.file_size:
                remove_sizes.setdefault(manifest_entry.file_size, []).append(
                    manifest_entry.content_hash
                )

        if remove_by_hash:
            matched_add = set()
            matched_remove = set()

            for i, add_entry in enumerate(to_add):
                add_path = Path(add_entry["path"])
                add_size = os.path.getsize(add_path)

                # Cheap pre-filter: skip if no removed file has the same size
                candidate_hashes = remove_sizes.get(add_size)
                if not candidate_hashes:
                    continue

                add_hash = file_content_hash(add_path)
                candidates = remove_by_hash.get(add_hash)
                if not candidates:
                    continue

                # Find the first unmatched candidate
                for rm_entry in candidates:
                    if rm_entry["path"] not in matched_remove:
                        matched_add.add(i)
                        matched_remove.add(rm_entry["path"])
                        to_rename.append({
                            "old_path": rm_entry["path"],
                            "new_path": add_entry["path"],
                            "filename": add_entry["filename"],
                            "old_filename": rm_entry["filename"],
                            "chunk_count": rm_entry["chunk_count"],
                            "game_system": rm_entry["game_system"],
                            "game_systems": list(rm_entry.get("game_systems", [])),
                            "content_hash": add_hash,
                        })
                        break

            # Remove matched entries from to_add and to_remove
            if matched_add:
                to_add = [e for i, e in enumerate(to_add) if i not in matched_add]
            if matched_remove:
                to_remove = [e for e in to_remove if e["path"] not in matched_remove]

    return {
        "to_add": to_add,
        "to_remove": to_remove,
        "to_auto_remove": to_auto_remove,
        "to_rename": to_rename,
        "to_update": to_update,
        "up_to_date": up_to_date,
        "errors": errors,
        "stale_paths": stale_paths,
        "outdated": outdated,
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

# Bound on concurrent searches (issue #344). Each search embeds its query
# through Ollama and may run the cross-encoder, so an unbounded fan-out
# spikes memory without buying throughput.
#
# Chosen by measurement, not intuition — 4 concurrent searches over the
# 17.8k-chunk eval corpus, best of 2 runs: 1 → 5.63s, 2 → 4.58s, 4 → 3.88s,
# 8 → 3.95s. Gains flatten at 4, where Ollama and the ONNX reranker
# saturate. Raise it only with a fresh measurement.
SEARCH_CONCURRENCY = 4
_search_semaphore = threading.Semaphore(SEARCH_CONCURRENCY)


@dataclass
class RequestContext:
    """The on-disk state one search reads, loaded once (issue #343).

    A single search used to re-read ``index_manifest.json`` up to four
    times — collection scope, source_filter/game_system resolution,
    secondary game-system tags, and the system soft-boost — plus
    ``search_settings.json`` and, when scoped, ``collections.json``. On a
    library of a few thousand PDFs that is megabytes of JSON parsed per
    keystroke-driven search. Reading them once per request is also more
    consistent, not less: the old reads could straddle a concurrent
    re-index and disagree with each other.
    """

    settings: SearchSettings
    manifest: IndexManifest
    collections: CollectionsStore | None = None


def _build_request_context(
    request: "SearchRequest", data_dir: Path | None
) -> RequestContext:
    """Read this request's settings/manifest (and the collections store
    only when the request is collection-scoped)."""
    if not data_dir:
        return RequestContext(
            settings=SearchSettings(), manifest=IndexManifest()
        )
    return RequestContext(
        settings=load_search_settings(data_dir),
        manifest=load_manifest(data_dir),
        collections=load_collections(data_dir) if request.collection else None,
    )


def _search_sync(
    request: "SearchRequest",
    *,
    store: LibraryStore,
    embed_fn,
    data_dir: Path | None,
    merged: dict,
    get_spell_corrector,
    get_lexical_index,
) -> dict:
    """Parent-document semantic search. Synchronous by nature.

    Every expensive step here blocks: the query embeds via a blocking HTTP
    call to Ollama, the cross-encoder is CPU-bound ONNX, and the
    manifest/store reads hit disk. It therefore must not run on the
    event loop — ``/api/search`` calls it through ``run_in_threadpool`` so
    one 5-7s search can't stall health polls, MCP heartbeats, or a streaming
    chat turn (issue #344).

    Over-fetches small embed units, dedupes by parent_id (keeping the
    highest-similarity hit per parent), then returns the corresponding
    parent text from the SQLite parents store. Per chunk_granularity_spike,
    dedupe-by-parent is a load-bearing part of the retrieval semantics —
    without it the user sees the same section repeated multiple times.
    """
    with _search_semaphore:
        # Spell correction (typo-tolerance design, section A): rewrite
        # OOV tokens to the closest library term before anything
        # consumes the query text — the dense embed, the reranker,
        # system detection, and the BM25 side all see the corrected
        # form. A clean query is a strict no-op (corrected is None).
        # Variant expansion (section B, default-off flag) then derives
        # spacing variants ("chainmail" ↔ "chain mail") of the
        # corrected query; they embed in the same call and fuse
        # below via RRF. Without them this is the single-query path —
        # zero overhead for the common case.
        # Effective pipeline knobs for this request: explicit request
        # fields win, then the persisted search settings, then the
        # built-in defaults. Settings, manifest and collections are read
        # once here and shared by every step below (issue #343).
        ctx = _build_request_context(request, data_dir)
        knobs = resolve_search_knobs(request, data_dir, settings=ctx.settings)

        corrected_query: str | None = None
        completed_query: str | None = None
        if knobs.spell_correction:
            # System keywords ("dnd", "osric") are cues for the boost,
            # which reads the corrected text: never rewrite them.
            protected = keyword_tokens(merged["known"])
            if request.partial:
                # A word still being typed is not a typo.
                protected |= {trailing_token(request.query)} - {""}
            corrector = get_spell_corrector(ctx.manifest)
            corrected_query = corrector.correct(
                request.query, protected=protected,
            )
            if request.partial:
                # Silent: the GM is still typing, so the box keeps what
                # they typed and only the search uses the completion.
                completed_query = corrector.complete(
                    corrected_query or request.query
                )
        query_text = completed_query or corrected_query or request.query
        # What is searched for: the query minus any system it names. The
        # system boost below still reads `query_text`.
        search_text = (
            strip_system_cues(query_text, merged["known"])
            if request.strip_cues else query_text
        )
        variant_queries: list[str] = []
        if knobs.variant_expansion:
            variant_queries = get_spell_corrector(ctx.manifest).expand(
                search_text
            )

        # Over-fetch by 10x so dedupe-by-parent still yields top-K parents.
        query_texts = [search_text, *variant_queries]
        n_candidates = request.n_results * 10

        # Scope, ANDed: which paths, which filename, which game systems.
        # `None` leaves that dimension open.
        scope_paths: set[str] | None = None
        scope_filename: str | None = None
        scope_systems: list[str] | None = None
        effective_collection = request.collection

        if effective_collection:
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )
            coll_store = ctx.collections
            if effective_collection not in coll_store.collections:
                raise HTTPException(
                    status_code=404,
                    detail=f"Collection not found: {effective_collection}",
                )
            coll_paths = resolve_collection_paths(
                coll_store.collections[effective_collection], ctx.manifest
            )
            if not coll_paths:
                return {
                    "results": [],
                    "message": "Collection has no indexed files.",
                    "effective_collection": effective_collection,
                    "exhausted": True,
                }
            scope_paths = set(coll_paths)
        if request.source_paths:
            scope_paths = (
                set(request.source_paths) if scope_paths is None
                else scope_paths & set(request.source_paths)
            )

        # source_filter / game_system arrive as guesses over user
        # vernacular ("dnd 5e", "Players Handbook.pdf") — mostly from
        # MCP agents. Exact-match-or-nothing turned every near-miss
        # into a silent empty result indistinguishable from a true
        # semantic miss (issue #309): resolve unambiguous near-misses
        # (noted in `message`), and turn unresolvable values into an
        # actionable message naming what is actually available.
        filter_notes: list[str] = []
        if corrected_query is not None:
            filter_notes.append(f'Query corrected to "{corrected_query}".')
        if data_dir and (request.source_filter or request.game_system):
            filt_manifest = ctx.manifest
            if request.source_filter:
                known_files = sorted(
                    {e.filename for e in filt_manifest.files.values()}
                )
                if request.source_filter not in known_files:
                    resolved, matches = _resolve_filter_value(
                        request.source_filter, known_files
                    )
                    if resolved is not None:
                        filter_notes.append(
                            f'source_filter "{request.source_filter}" '
                            f'matched "{resolved}".'
                        )
                        request.source_filter = resolved
                    else:
                        hint = (
                            f"Closest indexed filenames: "
                            f"{', '.join(sorted(matches))}."
                            if matches
                            else "Use the sources list for exact filenames."
                        )
                        return {
                            "results": [],
                            "message": (
                                f'No indexed file matches source_filter '
                                f'"{request.source_filter}". {hint}'
                            ),
                            "effective_collection": effective_collection,
                            "exhausted": True,
                        }
            if request.game_system:
                known_tags = sorted({
                    t for e in filt_manifest.files.values()
                    for t in {e.game_system, *e.game_systems} if t
                })
                if request.game_system not in known_tags:
                    resolved, matches = _resolve_filter_value(
                        request.game_system, known_tags
                    )
                    if resolved is not None:
                        filter_notes.append(
                            f'game_system "{request.game_system}" '
                            f'matched "{resolved}".'
                        )
                        request.game_system = resolved
                    else:
                        pool = sorted(matches) if matches else known_tags
                        return {
                            "results": [],
                            "message": (
                                f'game_system "{request.game_system}" is '
                                f'not in the library. Available: '
                                f'{", ".join(pool)}. Retry with an exact '
                                f'value or without the filter.'
                            ),
                            "effective_collection": effective_collection,
                            "exhausted": True,
                        }

        if request.source_filter:
            scope_filename = request.source_filter
        if request.game_system or request.game_systems:
            # A book matches on its primary tag or any secondary tag.
            requested = set(request.game_systems or [])
            if request.game_system:
                requested.add(request.game_system)
            scope_systems = sorted(requested)

        doc_ids = store.scope_document_ids(
            paths=sorted(scope_paths) if scope_paths is not None else None,
            filename=scope_filename,
            systems=scope_systems,
        )

        # One dense ranking per query text (the query plus its spacing
        # variants), in the shape the fusion below reads: per-ranking
        # lists of ids, metadatas, distances and texts.
        results: dict[str, list[list]] = {
            "ids": [], "metadatas": [], "distances": [], "documents": [],
        }
        rankings_raw = [
            store.knn(vec, n_candidates, doc_ids)
            for vec in embed_fn(query_texts)
        ]
        units = store.hydrate(
            list({uid for ranking in rankings_raw for uid, _ in ranking})
        )
        for ranking in rankings_raw:
            hits = [(uid, dist) for uid, dist in ranking if uid in units]
            results["ids"].append([uid for uid, _ in hits])
            results["metadatas"].append([units[uid].metadata for uid, _ in hits])
            results["distances"].append([dist for _, dist in hits])
            results["documents"].append([units[uid].text for uid, _ in hits])

        if not any(results["documents"]):
            return {
                "results": [],
                "message": " ".join([*filter_notes, "No results found."]),
                "corrected_query": corrected_query,
                "completed_query": completed_query,
                "effective_collection": effective_collection,
                "exhausted": True,
            }

        ordered_metadatas = results["metadatas"][0]
        ordered_distances = results["distances"][0]
        ordered_docs = results["documents"][0]

        # Multi-ranking fusion: the spacing-variant rankings (section
        # B) and — under the experimental default-off `hybrid` flag —
        # a BM25 ranking over the same chunks join the dense primary
        # via reciprocal-rank fusion, then the fused pool feeds the
        # boost/rerank/dedupe pipeline unchanged. The BM25 side
        # searches the same `doc_ids` scope as the dense side.
        # A candidate seen by several dense rankings reports its
        # minimum cosine distance; BM25-only candidates carry no
        # cosine distance — they get a sentinel 1.0 (relevance 0.0)
        # that the reranker replaces with a real cross-encoder score
        # when rerank is on.
        # Hybrid rerank pool (union): the head of the candidate order
        # plus the BM25 top-M, flagged here in `lex_top`. The fused
        # order alone can't admit BM25 hits — weighted RRF at k=60 ranks
        # a BM25-only #1 at w=0.3 like dense #143, so no BM25-only hit
        # ever reached a top-50 pool.
        lex_top: list[bool] | None = None
        if variant_queries or knobs.hybrid:
            rankings = list(results["ids"])
            dense_best: dict[int, tuple[dict, float, str]] = {}
            for ids, metas, dists, docs in zip(
                results["ids"], results["metadatas"],
                results["distances"], results["documents"],
            ):
                for cid, meta, dist, doc in zip(ids, metas, dists, docs):
                    if (
                        cid not in dense_best
                        or dist < dense_best[cid][1]
                    ):
                        dense_best[cid] = (meta, dist, doc)
            weights = [1.0] * len(rankings)
            lex_rows: dict[int, tuple[dict, str]] = {}
            if knobs.hybrid:
                lex = get_lexical_index()
                lex_ids = lex.search(
                    search_text, k=n_candidates, doc_ids=doc_ids,
                    prefix_last=request.partial,
                )
                rankings.append(lex_ids)
                weights.append(
                    request.lex_weight if request.lex_weight is not None
                    else LEXICAL_RRF_WEIGHT
                )
                lex_rows = lex.lookup(
                    [cid for cid in lex_ids if cid not in dense_best]
                )
            fused_metadatas, fused_distances = [], []
            fused_docs, fused_ids = [], []
            for cid, _score in rrf_fuse(rankings, weights):
                if cid in dense_best:
                    meta, dist, doc = dense_best[cid]
                    fused_metadatas.append(meta)
                    fused_distances.append(dist)
                    fused_docs.append(doc)
                elif cid in lex_rows:
                    meta, doc = lex_rows[cid]
                    fused_metadatas.append(meta)
                    fused_distances.append(1.0)
                    fused_docs.append(doc)
                else:
                    # A unit whose book was removed mid-search.
                    continue
                fused_ids.append(cid)
            ordered_metadatas = fused_metadatas
            ordered_distances = fused_distances
            ordered_docs = fused_docs
            if knobs.hybrid:
                lex_pool = (
                    request.lex_pool if request.lex_pool is not None
                    else LEXICAL_RERANK_POOL
                )
                top_ids = set(lex_ids[:lex_pool])
                lex_top = [cid in top_ids for cid in fused_ids]

        # Game-system boost (roadmap 3.3): when the query names a system
        # and the request isn't already scoped to one (or to a single
        # file), candidates from that system's sources move to the front
        # as a stable partition — here, so the rerank pool fills with the
        # named system, and again after rerank, so a wrong-system hit the
        # cross-encoder loves can't outrank them. Never a filter: the
        # rest follow in order. Distances (and so relevance/tier) are
        # untouched. Replaces the ×1.5/×0.7 multipliers, which lost to a
        # saturated cross-encoder score (0.92×0.7 > 0.39×1.5).
        matched: list[bool] | None = None
        if not (
            request.game_system or request.game_systems
            or request.source_filter
        ):
            target_systems = detect_systems_in_query(
                query_text, merged["known"]
            )
            if target_systems:
                matched = _system_matches(
                    ordered_metadatas, target_systems,
                    data_dir, merged["known"], manifest=ctx.manifest,
                )
                order = _front_first(matched)
                ordered_metadatas = [ordered_metadatas[i] for i in order]
                ordered_distances = [ordered_distances[i] for i in order]
                ordered_docs = [ordered_docs[i] for i in order]
                matched = [matched[i] for i in order]
                if lex_top is not None:
                    lex_top = [lex_top[i] for i in order]

        # Re-rank the top of the candidate pool with a cross-encoder.
        # Scoring (query, chunk-text) jointly is more accurate than raw
        # cosine, especially when several candidates are topically
        # adjacent. It reorders the pool outright: a blend with the
        # pool's retrieval order lost on every scope (2026-09-23, roadmap
        # 3.2) — BM25-admitted candidates sit at the pool's tail, so the
        # blend pinned down exactly what the union pool let in. Trailing
        # candidates keep retrieval order so the dedupe loop never
        # starves if a section has many slices.
        #
        # Section_heading is prepended to mirror what the embedder saw
        # (`_embed_text`). Without the breadcrumb the cross-encoder is
        # blind to whether a chunk is from a rule definition
        # ("Combat > Grappling") versus a creature card with the same
        # keyword ("Goblin > Actions"), and tends to over-rank the
        # keyword-dense action text.
        rerank_applied = False
        pool = 0
        if knobs.rerank and _rerank_safe_for_query(search_text):
            pool = min(knobs.rerank_candidates, len(ordered_metadatas))
            if lex_top is not None:
                # Stable partition: the head plus the BM25 top-M move to
                # the front in their current order — exactly the pool.
                in_union = [i < pool or t for i, t in enumerate(lex_top)]
                order = _front_first(in_union)
                ordered_metadatas = [ordered_metadatas[i] for i in order]
                ordered_distances = [ordered_distances[i] for i in order]
                ordered_docs = [ordered_docs[i] for i in order]
                if matched is not None:
                    matched = [matched[i] for i in order]
                pool = sum(in_union)
            pool_docs = ordered_docs[:pool]
            pool_meta = ordered_metadatas[:pool]
            rerank_inputs = [
                _with_heading(m.get("section_heading"), d, HEADING_RERANK)
                for m, d in zip(pool_meta, pool_docs)
            ]
            scores = rerank_scores(search_text, rerank_inputs)
            if scores is not None:
                rerank_applied = True
                order = sorted(
                    range(pool), key=lambda i: scores[i], reverse=True
                )
                if matched is not None:
                    matched = (
                        [matched[i] for i in order] + matched[pool:]
                    )
                head_metadatas = [ordered_metadatas[i] for i in order]
                # Use 1 - rerank_score so 1 - distance = rerank score
                # downstream, keeping the response shape unchanged.
                head_distances = [1.0 - scores[i] for i in order]
                head_docs = [ordered_docs[i] for i in order]
                ordered_metadatas = head_metadatas + ordered_metadatas[pool:]
                ordered_distances = head_distances + ordered_distances[pool:]
                ordered_docs = head_docs + ordered_docs[pool:]

        # Which candidates the cross-encoder scored, carried through the
        # post-rerank partition below.
        reranked = [rerank_applied and i < pool for i in range(len(ordered_docs))]
        if matched is not None:
            order = _front_first(matched)
            ordered_metadatas = [ordered_metadatas[i] for i in order]
            ordered_distances = [ordered_distances[i] for i in order]
            ordered_docs = [ordered_docs[i] for i in order]
            reranked = [reranked[i] for i in order]
            matched = [matched[i] for i in order]

        # Dedupe by assembled section, keeping the first hit per section
        # (the iteration order is the re-ranked-then-cosine order from
        # above). The store picks each candidate's section root before we
        # decide, so two hits inside one section collapse to one result
        # even when they sit in different parents. Legacy rows (no
        # section_path, or a source with no parent rows at all) keep the
        # old parent_id key.
        #
        # One connection for the whole loop, and `size_cache` memoises the
        # subtree aggregates for this request — candidates from the same
        # chapter otherwise re-sum that chapter's text once each.
        # `root_by_pid` then hands the roots to fetch_sections so they are
        # not computed a second time.
        size_cache: dict[tuple[str, str], tuple[int, int]] = {}
        root_by_pid: dict[str, str] = {}
        seen: set[str] = set()
        picked: list[dict] = []
        conn = store.conn()
        for i, (metadata, distance) in enumerate(
            zip(ordered_metadatas, ordered_distances)
        ):
            pid = metadata.get("parent_id")
            if not pid:
                continue
            path = metadata.get("section_path") or None
            source = metadata.get("source") or None
            root = None
            if path and source:
                root = section_root_for(
                    conn, source, path, cache=size_cache
                )
            if root is not None:
                root_by_pid[pid] = root
            key = root or pid
            if key in seen:
                continue
            seen.add(key)
            picked.append({
                "metadata": metadata,
                "distance": distance,
                "doc": ordered_docs[i],
                "reranked": reranked[i],
            })
            if len(picked) >= request.n_results:
                break

        # Whether a larger request could find more (roadmap 2.x): the
        # overfetch pool ran out before n_results distinct sections were
        # picked. Measured here, before near-dup collapse and packing —
        # those shorten the returned list without meaning the library has
        # nothing left, which is exactly the confusion that made
        # "fewer results than asked for" an unusable end-of-list signal
        # for the frontend's scroll-load.
        exhausted = len(picked) < request.n_results

        # Single-scale page (issue #306): when the reranker ran, picked
        # results from beyond the pool are scored with the cross-encoder
        # in one small batch (≤ n_results pairs), so every returned
        # relevance and tier is on one scale. Scores only: re-sorting
        # the tail into the head would undo the system-boost partition.
        # On failure the tail keeps its cosine score and reranked=False.
        if rerank_applied:
            stragglers = [p for p in picked if not p["reranked"]]
            if stragglers:
                straggler_scores = rerank_scores(search_text, [
                    _with_heading(
                        p["metadata"].get("section_heading"), p["doc"],
                        HEADING_RERANK,
                    )
                    for p in stragglers
                ])
                if straggler_scores is not None:
                    for p, sc in zip(stragglers, straggler_scores):
                        p["distance"] = 1.0 - sc
                        p["reranked"] = True

        # The section each hit is answered with, plus the hit's own
        # parent (one batched IN query) for the narrower `chunk_text`.
        sections = fetch_sections(
            store,
            [
                (
                    p["metadata"]["parent_id"],
                    p["metadata"].get("section_path") or None,
                    p["metadata"].get("source"),
                )
                for p in picked
            ],
            roots=root_by_pid,
            cache=size_cache,
        )
        parents = fetch_parents(
            store, [p["metadata"]["parent_id"] for p in picked]
        )

        formatted = []
        for p in picked:
            metadata = p["metadata"]
            distance = p["distance"]
            pid = metadata["parent_id"]
            sec = sections.get(pid)
            parent = parents.get(pid)
            # Fall back to the embed unit text if the rows are missing
            # (shouldn't happen post-reindex; defensive).
            text = sec.text if sec else p["doc"]
            chunk_text = parent.text if parent else p["doc"]
            # SectionDoc/ParentDoc.section_heading is Optional[str], so
            # the chain can leak None into the response. Trailing `or ""`
            # coerces back to a string — the Tauri SearchResultItem
            # decoder requires String, not null, and would otherwise
            # reject the whole response.
            section_heading = (
                (sec.section_heading if sec else None)
                or metadata.get("section_heading")
                or ""
            )
            relevance = round(max(0.0, min(1.0, 1 - distance)), 3)
            page_start = sec.page_start if sec else metadata.get("page_start", 0)
            page_end = sec.page_end if sec else metadata.get("page_end", 0)
            # The printed labels describe the matched unit's pages. When the
            # returned span is the wider section, they would mislabel it
            # ("p.326 (PDF pp.324-331)"), so blank them — blank means "cite
            # the physical span" downstream (mcp_server._page_span).
            same_span = (page_start, page_end) == (
                metadata.get("page_start", 0), metadata.get("page_end", 0)
            )
            formatted.append({
                "text": text,
                # The unit that actually matched, and the parent it sits
                # in — `text` is now the whole section, so a consumer
                # that wants the narrow hit needs it named.
                "matched_text": p["doc"],
                "chunk_text": chunk_text,
                "section_id": (
                    sec.section_id if sec else (metadata.get("section_id") or "")
                ),
                "section_path": (
                    sec.root_path if sec else (metadata.get("section_path") or "")
                ),
                "filename": metadata["filename"],
                "source": metadata.get("source", ""),
                "section_heading": section_heading,
                "page_start": page_start,
                "page_end": page_end,
                # The number printed on the paper, "" when it matches the
                # physical page. A citation a GM cannot find at the table is
                # not a citation.
                "page_label_start": (
                    metadata.get("page_label_start", "") if same_span else ""
                ),
                "page_label_end": (
                    metadata.get("page_label_end", "") if same_span else ""
                ),
                "game_system": metadata.get("game_system") or "unknown",
                "relevance": relevance,
                "tier": _tier_for(relevance, p["reranked"]),
                "reranked": p["reranked"],
            })

        # Cross-edition twins (roadmap 2.3): fold before packing, so the
        # budget sees the collapsed list. May shorten it below n_results.
        formatted = collapse_near_dups(formatted)
        formatted = pack_results(formatted, request.max_context_chars)

        response: dict = {
            "results": formatted,
            "corrected_query": corrected_query,
            "completed_query": completed_query,
            "effective_collection": effective_collection,
            "exhausted": exhausted,
        }
        if filter_notes:
            response["message"] = " ".join(filter_notes)
        return response


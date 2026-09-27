"""Post-extraction cleanup rules for pymupdf4llm Markdown.

Four rules, applied between ``pymupdf4llm.to_markdown()`` (with
heading-hierarchy promotion) and the chunker:

  R1 — rejoin per-word fragments separated by bare ``\\r`` (narrow
       two-column layouts; SRD).
  R2 — strip running headers/footers detected by zone-anchored
       paragraph-frequency rule plus a tail-zone structural backstop.
  R3 — strip pymupdf4llm's literal image placeholders and unwrap
       picture-text marker pairs.
  R4 — strip cross-page recurring head/tail-zone heading lines
       (e.g. ``## BASIC FANTASY RPG`` chrome that pymupdf4llm emits
       as a heading rather than a paragraph; R2 skips heading lines
       so this rule is its mirror for ``^#+\\s+`` chrome).

R1, R2, R3 validated by the extraction_quality_spike. R4 added in
issue #157 alongside heading-hierarchy promotion adoption.

Cleanup operates on Markdown content only. Page provenance
(``page_start`` / ``page_end``) is set per-page during extraction and
is intentionally not touched here — the issue #113 contract holds.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


# ─────────────────────────── R1 ───────────────────────────

_CR_FRAGMENT_RE = re.compile(r"[\r]+[ \t]*")


def rejoin_cr_fragments(markdown: str) -> tuple[str, int]:
    """Collapse CR-separated word fragments back into single-spaced text.

    pymupdf4llm uses bare ``\\r`` as the intra-paragraph separator on
    narrow-column layouts and ``\\n\\n`` for real paragraph breaks. The
    substitution never matches ``\\n``, so headings and pipe tables are
    structurally safe.
    """
    cleaned, n = _CR_FRAGMENT_RE.subn(" ", markdown)
    if n == 0:
        return markdown, 0
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned, n


# ─────────────────────────── R3 ───────────────────────────

_PICTURE_OMITTED_RE = re.compile(
    r"\*\*\s*==>\s*picture\s*\[[^\]]+\]\s*intentionally\s*omitted\s*<==\s*\*\*",
    re.IGNORECASE,
)
_PICTURE_TEXT_BLOCK_RE = re.compile(
    r"\*\*-{3,}\s*Start of picture text\s*-{3,}\*\*\s*<br>?\s*"
    r"(.*?)"
    r"\*\*-{3,}\s*End of picture text\s*-{3,}\*\*\s*<br>?",
    re.DOTALL | re.IGNORECASE,
)


def strip_image_placeholders(markdown: str) -> tuple[str, int, int]:
    """Strip pymupdf4llm's image-related chrome.

    Both patterns are anchored on pymupdf4llm's exact phrasing — body
    content cannot collide.

    R3a strips ``**==> picture [WxH] intentionally omitted <==**``
    entirely. R3b unwraps ``**----- Start/End of picture text -----**``
    markers and keeps the inner OCR'd content as a regular paragraph.
    """
    cleaned, n_omitted = _PICTURE_OMITTED_RE.subn("", markdown)
    cleaned, n_unwrapped = _PICTURE_TEXT_BLOCK_RE.subn(
        lambda m: m.group(1).strip(), cleaned
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, n_omitted, n_unwrapped


# ─────────────────────────── R2 ───────────────────────────

_PAGE_NUM_RE = re.compile(r"\d+")
_HEAD_PARAGRAPHS = 3
_TAIL_PARAGRAPHS = 3

# Frequency cutoff: paragraphs appearing in the same zone on >=
# _DEFAULT_THRESHOLD of pages are classified as running. 0.40 is the
# empirical sweet spot validated on three publishers in the spike;
# tune here if onboarding new publishers (lower if artifacts survive,
# raise if legitimate body content is being stripped).
_DEFAULT_THRESHOLD = 0.40

# Tail-zone structural backstop: bold + leading digits + optional
# section title (e.g. ``**150 Spellcasting**``). Catches per-section
# footers that the frequency rule misses because each section
# normalizes to a unique string. ``^...$`` plus stripped paragraph
# means a body sentence with ``**150 gold pieces**`` mid-paragraph
# never matches.
_STRUCTURAL_FOOTER_RE = re.compile(r"^\*\*\d+(?:\s+[^*]+)?\*\*$")


@dataclass(frozen=True)
class RunningElement:
    zone: str
    normalized: str
    pages_seen: int


def _normalize(text: str) -> str:
    return _PAGE_NUM_RE.sub("#", " ".join(text.split()))


def _is_skippable(paragraph: str) -> bool:
    """Headings and pipe-table rows are never classified as running."""
    s = paragraph.lstrip()
    return s.startswith("#") or s.startswith("|")


def _split_paragraphs(markdown: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", markdown) if p.strip()]


def _zoned_candidates(paragraphs: list[str]) -> list[tuple[str, int]]:
    """Yield (zone, paragraph_index) for head/tail inspection windows.

    Body paragraphs are never candidates — the head/tail restriction
    is the false-positive guard.
    """
    out: list[tuple[str, int]] = []
    seen = 0
    for i, p in enumerate(paragraphs):
        if _is_skippable(p):
            continue
        out.append(("head", i))
        seen += 1
        if seen >= _HEAD_PARAGRAPHS:
            break
    seen = 0
    for i in range(len(paragraphs) - 1, -1, -1):
        if _is_skippable(paragraphs[i]):
            continue
        out.append(("tail", i))
        seen += 1
        if seen >= _TAIL_PARAGRAPHS:
            break
    return out


def detect_running_elements(
    pages_markdown: list[str],
    threshold: float = _DEFAULT_THRESHOLD,
) -> list[RunningElement]:
    """Detect normalized paragraphs repeating in the same zone on
    >= threshold of pages. Pure detection — does not modify input.

    Position within a zone (head_0 vs head_1) is intentionally ignored:
    a header may be preceded by a chapter title on some pages but not
    others, so positional bucketing misses real running elements
    (validated empirically in the spike).
    """
    counts: Counter[tuple[str, str]] = Counter()
    page_count = len(pages_markdown)
    if page_count == 0:
        return []
    for md in pages_markdown:
        paragraphs = _split_paragraphs(md)
        seen_in_page: set[tuple[str, str]] = set()
        for zone, idx in _zoned_candidates(paragraphs):
            key = (zone, _normalize(paragraphs[idx]))
            if key in seen_in_page:
                continue
            seen_in_page.add(key)
            counts[key] += 1
    cutoff = max(2, int(page_count * threshold))
    return [
        RunningElement(zone=zone, normalized=norm, pages_seen=n)
        for (zone, norm), n in counts.items()
        if n >= cutoff
    ]


def _matches_structural_footer(paragraph: str) -> bool:
    return bool(_STRUCTURAL_FOOTER_RE.match(paragraph.strip()))


def strip_running_elements(
    pages_markdown: list[str],
    running: list[RunningElement],
) -> tuple[list[str], int]:
    """Strip detected running elements + tail-zone structural footers.

    Returns (cleaned_pages, total_paragraphs_stripped). Pages are
    re-joined with ``\\n\\n`` after stripping; downstream consumers
    (the chunker, ``_flatten_br_packed_cells``) are whitespace-agnostic.
    """
    by_zone: dict[str, set[str]] = {}
    for elt in running:
        by_zone.setdefault(elt.zone, set()).add(elt.normalized)
    out_pages: list[str] = []
    stripped = 0
    for md in pages_markdown:
        paragraphs = _split_paragraphs(md)
        drop_indices: set[int] = set()
        for zone, idx in _zoned_candidates(paragraphs):
            text = paragraphs[idx]
            if _normalize(text) in by_zone.get(zone, set()):
                drop_indices.add(idx)
                continue
            if zone == "tail" and _matches_structural_footer(text):
                drop_indices.add(idx)
        if drop_indices:
            stripped += len(drop_indices)
            paragraphs = [p for i, p in enumerate(paragraphs) if i not in drop_indices]
        out_pages.append("\n\n".join(paragraphs))
    return out_pages, stripped


# ─────────────────────────── R4 ───────────────────────────

_HEADING_LINE_RE = re.compile(r"^#{1,12}\s+(.+?)\s*$")
_HEAD_LINES_ZONE = 5
_TAIL_LINES_ZONE = 5


@dataclass(frozen=True)
class RunningHeading:
    zone: str
    normalized: str
    pages_seen: int


def _heading_zoned_candidates(md: str) -> list[tuple[str, int, str]]:
    """Yield (zone, line_index, heading_text) for head/tail heading lines.

    Inspects the first ``_HEAD_LINES_ZONE`` and last ``_TAIL_LINES_ZONE``
    non-blank lines for ``^#+\\s+...$`` patterns. Line-scoped (not
    paragraph-scoped) because pymupdf4llm's heading-as-chrome leaks
    appear as standalone heading lines, not embedded in paragraphs.
    """
    lines = md.split("\n")
    out: list[tuple[str, int, str]] = []
    head_seen = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        m = _HEADING_LINE_RE.match(line)
        if m:
            out.append(("head", i, m.group(1).strip()))
        head_seen += 1
        if head_seen >= _HEAD_LINES_ZONE:
            break
    tail_seen = 0
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].strip():
            continue
        m = _HEADING_LINE_RE.match(lines[i])
        if m:
            out.append(("tail", i, m.group(1).strip()))
        tail_seen += 1
        if tail_seen >= _TAIL_LINES_ZONE:
            break
    return out


def detect_running_headings(
    pages_markdown: list[str],
    threshold: float = _DEFAULT_THRESHOLD,
) -> list[RunningHeading]:
    """Detect normalized heading text repeating in the same head/tail
    zone across ``>= threshold`` of pages. Pure detection — does not
    modify input. Reuses R2's ``_normalize`` for digit-substitution.
    """
    counts: Counter[tuple[str, str]] = Counter()
    page_count = len(pages_markdown)
    if page_count == 0:
        return []
    for md in pages_markdown:
        seen_in_page: set[tuple[str, str]] = set()
        for zone, _idx, text in _heading_zoned_candidates(md):
            key = (zone, _normalize(text))
            if key in seen_in_page:
                continue
            seen_in_page.add(key)
            counts[key] += 1
    cutoff = max(2, int(page_count * threshold))
    return [
        RunningHeading(zone=zone, normalized=norm, pages_seen=n)
        for (zone, norm), n in counts.items()
        if n >= cutoff
    ]


def strip_running_headings(
    pages_markdown: list[str],
    running: list[RunningHeading],
) -> tuple[list[str], int]:
    """Drop matching head/tail-zone heading lines per page.

    Returns ``(cleaned_pages, total_lines_stripped)``. Pages re-join
    with ``\\n`` (line-scoped operation, unlike R2's paragraph rejoin).
    """
    by_zone: dict[str, set[str]] = {}
    for elt in running:
        by_zone.setdefault(elt.zone, set()).add(elt.normalized)
    out_pages: list[str] = []
    stripped = 0
    for md in pages_markdown:
        drop_indices: set[int] = set()
        for zone, idx, text in _heading_zoned_candidates(md):
            if _normalize(text) in by_zone.get(zone, set()):
                drop_indices.add(idx)
        if not drop_indices:
            out_pages.append(md)
            continue
        lines = md.split("\n")
        kept = [l for i, l in enumerate(lines) if i not in drop_indices]
        stripped += len(drop_indices)
        out_pages.append("\n".join(kept))
    return out_pages, stripped


# ─────────────────────────── orchestration ───────────────────────────


@dataclass(frozen=True)
class CleanupReport:
    cr_substitutions: int = 0
    paragraphs_stripped: int = 0
    headings_stripped: int = 0
    images_omitted_stripped: int = 0
    picture_text_unwrapped: int = 0
    running_elements: tuple[RunningElement, ...] = field(default_factory=tuple)
    running_headings: tuple[RunningHeading, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        elts = ", ".join(
            f"{e.zone}:{e.normalized!r}({e.pages_seen})"
            for e in sorted(self.running_elements, key=lambda r: -r.pages_seen)
        )
        head_elts = ", ".join(
            f"{h.zone}:{h.normalized!r}({h.pages_seen})"
            for h in sorted(self.running_headings, key=lambda r: -r.pages_seen)
        )
        return (
            f"R1 cr_subs={self.cr_substitutions} | "
            f"R2 stripped={self.paragraphs_stripped} elts=[{elts}] | "
            f"R3 omitted={self.images_omitted_stripped} unwrapped={self.picture_text_unwrapped} | "
            f"R4 stripped={self.headings_stripped} elts=[{head_elts}]"
        )


def clean_pages(
    pages_markdown: list[str],
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[list[str], CleanupReport]:
    """Run R1 → R3 → R4 → R2 in order on a per-page Markdown list.

    Order is load-bearing: R1 first because CR-fragmented content
    would otherwise interrupt R3's literal patterns; R3 before the
    cross-page passes because stripping image-placeholder paragraphs
    yields cleaner head/tail-zone candidates. R4 before R2 keeps the
    two cross-page passes adjacent (same zone semantics, different
    element types).
    """
    cr_total = 0
    omitted_total = 0
    unwrapped_total = 0
    after_r1r3: list[str] = []
    for md in pages_markdown:
        md, n_cr = rejoin_cr_fragments(md)
        md, n_omit, n_unwrap = strip_image_placeholders(md)
        cr_total += n_cr
        omitted_total += n_omit
        unwrapped_total += n_unwrap
        after_r1r3.append(md)
    running_headings = detect_running_headings(after_r1r3, threshold=threshold)
    after_r4, headings_stripped = strip_running_headings(after_r1r3, running_headings)
    running = detect_running_elements(after_r4, threshold=threshold)
    cleaned, stripped = strip_running_elements(after_r4, running)
    report = CleanupReport(
        cr_substitutions=cr_total,
        paragraphs_stripped=stripped,
        headings_stripped=headings_stripped,
        images_omitted_stripped=omitted_total,
        picture_text_unwrapped=unwrapped_total,
        running_elements=tuple(running),
        running_headings=tuple(running_headings),
    )
    return cleaned, report

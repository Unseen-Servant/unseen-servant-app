"""Post-extraction cleanup rules for pymupdf4llm Markdown.

Three rules, validated by the extraction_quality_spike (sibling repo
unseen-legend-lore-experiments) and applied between
``pymupdf4llm.to_markdown()`` and the chunker:

  R1 — rejoin per-word fragments separated by bare ``\\r`` (narrow
       two-column layouts; SRD).
  R2 — strip running headers/footers detected by zone-anchored
       frequency rule plus a tail-zone structural backstop.
  R3 — strip pymupdf4llm's literal image placeholders and unwrap
       picture-text marker pairs.

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


# ─────────────────────────── orchestration ───────────────────────────


@dataclass(frozen=True)
class CleanupReport:
    cr_substitutions: int = 0
    paragraphs_stripped: int = 0
    images_omitted_stripped: int = 0
    picture_text_unwrapped: int = 0
    running_elements: tuple[RunningElement, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        elts = ", ".join(
            f"{e.zone}:{e.normalized!r}({e.pages_seen})"
            for e in sorted(self.running_elements, key=lambda r: -r.pages_seen)
        )
        return (
            f"R1 cr_subs={self.cr_substitutions} | "
            f"R2 stripped={self.paragraphs_stripped} elts=[{elts}] | "
            f"R3 omitted={self.images_omitted_stripped} unwrapped={self.picture_text_unwrapped}"
        )


def clean_pages(
    pages_markdown: list[str],
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[list[str], CleanupReport]:
    """Run R1 → R3 → R2 in order on a per-page Markdown list.

    Order is load-bearing: R1 first because CR-fragmented content
    would otherwise interrupt R3's literal patterns; R3 before R2
    because stripping image-placeholder paragraphs yields cleaner
    head/tail-zone candidates for R2.
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
    running = detect_running_elements(after_r1r3, threshold=threshold)
    cleaned, stripped = strip_running_elements(after_r1r3, running)
    report = CleanupReport(
        cr_substitutions=cr_total,
        paragraphs_stripped=stripped,
        images_omitted_stripped=omitted_total,
        picture_text_unwrapped=unwrapped_total,
        running_elements=tuple(running),
    )
    return cleaned, report

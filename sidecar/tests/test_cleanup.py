"""Unit tests for the post-extraction cleanup rules (R1/R2/R3).

Pure string-in/string-out tests — no IO, no PDFs. The rules run between
``pymupdf4llm.to_markdown()`` and the chunker; bugs here corrupt every
indexed chunk on the affected publishers.

Validated end-to-end in the extraction_quality_spike (sibling repo
unseen-legend-lore-experiments). These tests pin the contract so future
changes can't silently break it.
"""

from cleanup import (
    CleanupReport,
    RunningElement,
    RunningHeading,
    clean_pages,
    detect_running_elements,
    detect_running_headings,
    rejoin_cr_fragments,
    strip_image_placeholders,
    strip_running_elements,
    strip_running_headings,
)


# ─────────────────────────── R1 ───────────────────────────


def test_r1_empty_input():
    assert rejoin_cr_fragments("") == ("", 0)


def test_r1_no_cr_is_noop():
    md = "Plain prose with no carriage returns.\n\nA second paragraph."
    cleaned, n = rejoin_cr_fragments(md)
    assert cleaned == md
    assert n == 0


def test_r1_collapses_per_word_fragments():
    """SRD's narrow-column case: bare \\r between every word."""
    fragmented = "If \r  you \r  note \r  any \r  errors"
    cleaned, n = rejoin_cr_fragments(fragmented)
    assert cleaned == "If you note any errors"
    assert n == 4


def test_r1_preserves_paragraph_breaks():
    """\\n\\n boundaries must survive — the regex doesn't match \\n."""
    md = "first \r  word\n\nsecond \r  paragraph"
    cleaned, _ = rejoin_cr_fragments(md)
    assert cleaned == "first word\n\nsecond paragraph"


def test_r1_preserves_headings_and_tables():
    """Headings and pipe tables don't contain \\r — must stay intact."""
    md = "## Heading\n\n| col1 | col2 |\n|---|---|\n| a \r  b | c |"
    cleaned, _ = rejoin_cr_fragments(md)
    assert "## Heading" in cleaned
    assert "| col1 | col2 |" in cleaned
    assert "| a b | c |" in cleaned


def test_r1_collapses_double_spaces():
    """word \\r  word → 'word  word' would have a double space; collapse it."""
    cleaned, _ = rejoin_cr_fragments("word \r  next")
    assert cleaned == "word next"


# ─────────────────────────── R3a ───────────────────────────


def test_r3a_strips_picture_omitted_placeholder():
    md = (
        "Some prose before.\n\n"
        "**==> picture [228 x 26] intentionally omitted <==**\n\n"
        "Some prose after."
    )
    cleaned, n_omitted, n_unwrapped = strip_image_placeholders(md)
    assert "intentionally omitted" not in cleaned
    assert "Some prose before." in cleaned
    assert "Some prose after." in cleaned
    assert n_omitted == 1
    assert n_unwrapped == 0


def test_r3a_strips_multiple_placeholders():
    md = (
        "**==> picture [10 x 10] intentionally omitted <==**\n\n"
        "Body.\n\n"
        "**==> picture [99 x 99] intentionally omitted <==**"
    )
    cleaned, n_omitted, _ = strip_image_placeholders(md)
    assert "intentionally omitted" not in cleaned
    assert n_omitted == 2


def test_r3a_no_match_when_pattern_absent():
    md = "Plain prose. The word picture appears but not the placeholder."
    cleaned, n_omitted, n_unwrapped = strip_image_placeholders(md)
    assert cleaned == md
    assert n_omitted == 0
    assert n_unwrapped == 0


# ─────────────────────────── R3b ───────────────────────────


def test_r3b_unwraps_picture_text_block():
    """Markers stripped, OCR'd inner content kept as a paragraph."""
    md = (
        "Some prose before.\n\n"
        "**----- Start of picture text -----**<br>\n"
        "ABILITY   ABILITY<br>SCORE MODIFIER SCORE MODIFIER<br>"
        "**----- End of picture text -----**<br>\n\n"
        "Some prose after."
    )
    cleaned, _, n_unwrapped = strip_image_placeholders(md)
    assert "Start of picture text" not in cleaned
    assert "End of picture text" not in cleaned
    assert "ABILITY" in cleaned
    assert "SCORE MODIFIER" in cleaned
    assert n_unwrapped == 1


def test_r3b_empty_inner_body_collapses_cleanly():
    """Edge case: empty picture-text block must not leave a blank chunk."""
    md = (
        "Before.\n\n"
        "**----- Start of picture text -----**<br>"
        "**----- End of picture text -----**<br>\n\n"
        "After."
    )
    cleaned, _, n_unwrapped = strip_image_placeholders(md)
    assert n_unwrapped == 1
    assert "Start of picture text" not in cleaned
    assert "Before." in cleaned and "After." in cleaned
    assert "\n\n\n" not in cleaned


# ─────────────────────────── R2 detect ───────────────────────────


def _page(*paragraphs: str) -> str:
    return "\n\n".join(paragraphs)


def test_r2_empty_input_returns_no_elements():
    assert detect_running_elements([]) == []


def test_r2_single_page_is_noop():
    """Built-in cutoff = max(2, ...) blocks single-page PDFs."""
    page = _page("BASIC FANTASY RPG", "## Chapter", "Body content here.", "1")
    assert detect_running_elements([page]) == []


def test_r2_detects_repeated_head_paragraph():
    pages = [
        _page("BASIC FANTASY RPG", "Body sentence one.", "Body sentence two.")
        for _ in range(10)
    ]
    elements = detect_running_elements(pages, threshold=0.40)
    assert any(
        e.zone == "head" and e.normalized == "BASIC FANTASY RPG"
        for e in elements
    )


def test_r2_normalizes_page_numbers():
    """Page numbers vary — digit normalization (\\d+ → #) merges them."""
    pages = [_page("Body.", f"System Reference Document 5.1 {n}") for n in range(20)]
    elements = detect_running_elements(pages, threshold=0.40)
    tail_norms = [e.normalized for e in elements if e.zone == "tail"]
    assert any("System Reference Document #.# #" == n for n in tail_norms)


def test_r2_threshold_cutoff_excludes_chapter_titles():
    """At 0.40, 'MONSTERS' on 32% of pages should not be flagged."""
    pages = [_page("MONSTERS", "Body.") for _ in range(32)]
    pages += [_page("PLAYERS", "Body.") for _ in range(68)]
    elements = detect_running_elements(pages, threshold=0.40)
    head_norms = [e.normalized for e in elements if e.zone == "head"]
    assert "MONSTERS" not in head_norms
    assert "PLAYERS" in head_norms


def test_r2_skips_markdown_headings_in_zones():
    """A heading in head_0 must never be candidate-counted."""
    pages = [_page("## Combat", "BASIC FANTASY RPG", "Body.") for _ in range(10)]
    elements = detect_running_elements(pages, threshold=0.40)
    head_norms = [e.normalized for e in elements if e.zone == "head"]
    assert "## Combat" not in head_norms
    assert "BASIC FANTASY RPG" in head_norms


def test_r2_skips_pipe_tables_in_zones():
    pages = [_page("| col | val |", "BASIC FANTASY RPG", "Body.") for _ in range(10)]
    elements = detect_running_elements(pages, threshold=0.40)
    head_norms = [e.normalized for e in elements if e.zone == "head"]
    assert not any(n.startswith("| col") for n in head_norms)


# ─────────────────────────── R2 strip ───────────────────────────


def test_r2_strip_removes_detected_elements():
    pages = [_page("BASIC FANTASY RPG", "Body content.") for _ in range(5)]
    running = [RunningElement(zone="head", normalized="BASIC FANTASY RPG", pages_seen=5)]
    cleaned, n = strip_running_elements(pages, running)
    assert n == 5
    for page in cleaned:
        assert "BASIC FANTASY RPG" not in page
        assert "Body content." in page


def test_r2_structural_backstop_strips_per_section_footer():
    """**150 Spellcasting** is unique per section so frequency rule misses it.
    The structural backstop catches it by shape."""
    pages = [_page("Body.", "**150 Spellcasting**")]
    cleaned, n = strip_running_elements(pages, running=[])
    assert n == 1
    assert "150 Spellcasting" not in cleaned[0]


def test_r2_structural_backstop_does_not_strip_body_bold_numbers():
    """**150 gold pieces** mid-paragraph must NOT match — the regex is
    anchored on the entire stripped paragraph, and body content is never
    in the tail zone."""
    pages = [_page("The chest contains **150 gold pieces** scattered.", "Footer line.")]
    cleaned, _ = strip_running_elements(pages, running=[])
    assert "**150 gold pieces**" in cleaned[0]


def test_r2_structural_backstop_only_in_tail_zone():
    """A bold-page-number paragraph in the head zone should not be stripped
    by the structural rule (head footers don't make sense). Page must be
    long enough that head and tail zones don't overlap.
    """
    pages = [_page(
        "**150 Spellcasting**",   # head_0 — must NOT match (head zone)
        "Body line one.",
        "Body line two.",
        "Body line three.",
        "Body line four.",
        "Body line five.",
        "Body line six.",
        "Real footer.",
    )]
    cleaned, n = strip_running_elements(pages, running=[])
    assert n == 0
    assert "**150 Spellcasting**" in cleaned[0]


def test_r2_known_limitation_strips_repeated_chapter_intro():
    """KNOWN LIMITATION: R2 will strip legitimate body content if a
    chapter-opener paragraph genuinely repeats in the head zone on >40% of
    pages. This is by design — the rule is repetition-based and can't
    distinguish "running header" from "actual repeated content". Future
    maintainers should not "fix" this without a real signal that goes
    beyond repetition.
    """
    unique_bodies = [
        "Goblins ambush the party in the forest road.",
        "The wizard prepares a fireball for the next encounter.",
        "Dwarven runes glow on the ancient stone door.",
        "A merchant offers cursed amulets in the market square.",
        "Owlbears nest in the abandoned watchtower.",
        "The cleric senses undead lurking nearby.",
        "Hobgoblin scouts patrol the bridge at dusk.",
        "Pirate captains negotiate with sea hags.",
        "The ranger tracks lycanthrope prints to a cave.",
        "Bards collect songs of long-dead emperors.",
    ]
    pages = [
        _page(
            "In this chapter you will learn about combat.",  # head_0 (running)
            unique_bodies[i],
            unique_bodies[(i + 1) % 10],
            unique_bodies[(i + 2) % 10],
            unique_bodies[(i + 3) % 10],
            unique_bodies[(i + 4) % 10],
        )
        for i in range(10)
    ]
    running = detect_running_elements(pages, threshold=0.40)
    cleaned, n = strip_running_elements(pages, running)
    assert n == 10
    for page in cleaned:
        assert "In this chapter" not in page


# ─────────────────────────── orchestration ───────────────────────────


def test_clean_pages_preserves_per_page_count_and_order():
    """Each input page must produce exactly one output page in the same order.
    Per-page index is what the caller uses to re-attach page_number."""
    pages = [
        _page("BASIC FANTASY RPG", "Page one body."),
        _page("BASIC FANTASY RPG", "Page two body."),
        _page("BASIC FANTASY RPG", "Page three body."),
    ]
    cleaned, _ = clean_pages(pages)
    assert len(cleaned) == 3
    assert "Page one body." in cleaned[0]
    assert "Page two body." in cleaned[1]
    assert "Page three body." in cleaned[2]


def test_clean_pages_runs_all_three_rules():
    """Synthetic page-list with all three defects → all cleaned. Pages
    have enough body content to keep the fragmented prose out of the
    head/tail zone."""
    pages = []
    for i in range(10):
        pages.append(
            "BASIC FANTASY RPG\n\n"                                          # head (running)
            "## Chapter\n\n"                                                 # heading, skipped
            "**==> picture [10 x 10] intentionally omitted <==**\n\n"        # R3
            f"Page heading sentence {i} unique to this page.\n\n"            # head, varies
            f"Page subheading {i} also unique.\n\n"                          # head, varies
            "Some \r  fragmented \r  prose \r  here.\n\n"                    # body, R1
            f"Body sentence A page {i} unique.\n\n"                          # body
            f"Body sentence B page {i} unique.\n\n"                          # body
            f"Tail sentence A page {i} unique.\n\n"                          # tail, varies
            f"Tail sentence B page {i} unique.\n\n"                          # tail, varies
            f"{i}"                                                           # tail (running, →#)
        )
    cleaned, report = clean_pages(pages)
    assert report.cr_substitutions > 0
    assert report.images_omitted_stripped == 10
    assert report.paragraphs_stripped > 0
    for page in cleaned:
        assert "BASIC FANTASY RPG" not in page
        assert "intentionally omitted" not in page
        assert "Some fragmented prose here." in page


def test_clean_pages_empty_list():
    cleaned, report = clean_pages([])
    assert cleaned == []
    assert report == CleanupReport()


def test_clean_pages_single_page_does_not_crash():
    """R2 detection must handle single-page input cleanly (cutoff guard)."""
    pages = ["## Title\n\nBody content."]
    cleaned, report = clean_pages(pages)
    assert len(cleaned) == 1
    assert report.paragraphs_stripped == 0


# ─────────────────────────── flattener compatibility ───────────────────────────


# ─────────────────────────── R4 ───────────────────────────


def test_r4_empty_input():
    assert detect_running_headings([]) == []
    assert strip_running_headings([], []) == ([], 0)


def _page_with_chrome_and_body(chrome_heading: str, body_lines: int = 10) -> str:
    """Build a page where the chrome heading is at the top and the
    page has enough body content that head and tail zones don't
    overlap. Mirrors real-PDF page structure."""
    body = "\n\n".join(f"Body paragraph {i}." for i in range(body_lines))
    return f"{chrome_heading}\n\n{body}"


def test_r4_detects_basic_running_heading():
    """`## BASIC FANTASY RPG` recurring as the first heading on most
    pages is the canonical R4 leak — pymupdf4llm emits running header
    chrome as a heading, R2 ignores headings, the chunker propagates
    it through the heading stack."""
    pages = [_page_with_chrome_and_body("## BASIC FANTASY RPG")] * 8 + [
        "No chrome here.\n\nJust body."
    ] * 2
    running = detect_running_headings(pages)
    assert any("BASIC" in r.normalized for r in running if r.zone == "head")
    cleaned, stripped = strip_running_headings(pages, running)
    assert stripped >= 8
    assert all("BASIC FANTASY RPG" not in p for p in cleaned[:8])


def test_r4_threshold_floor_two_pages():
    """Cutoff is `max(2, int(N * threshold))`. Default 0.40 on 5 pages
    gives `max(2, 2) = 2` — the chrome appearing on exactly 2 pages
    still strips."""
    pages = [
        _page_with_chrome_and_body("## BOOK TITLE"),
        _page_with_chrome_and_body("## BOOK TITLE"),
        "Plain page.\n\nMore body.",
        "Plain page.\n\nMore body.",
        "Plain page.\n\nMore body.",
    ]
    running = detect_running_headings(pages)
    head_running = [r for r in running if r.zone == "head"]
    assert len(head_running) == 1
    cleaned, stripped = strip_running_headings(pages, running)
    assert stripped == 2


def test_r4_high_threshold_does_not_strip():
    """At a 0.60 threshold, 2-of-5 falls below the cutoff and the
    heading is preserved as legitimate body content."""
    pages = [
        _page_with_chrome_and_body("## BOOK TITLE"),
        _page_with_chrome_and_body("## BOOK TITLE"),
        "Plain page.\n\nMore body.",
        "Plain page.\n\nMore body.",
        "Plain page.\n\nMore body.",
    ]
    running = detect_running_headings(pages, threshold=0.60)
    assert running == []


def test_r4_zone_discrimination_keeps_body_headings():
    """A heading appearing as the *first* heading on every page is
    chrome; the same heading text appearing in the *body* of every
    page (line 20+) is legitimate content. Zone restriction prevents
    stripping body chapter titles that happen to recur."""
    body_buffer = "\n\n".join([f"Paragraph {i}." for i in range(15)])
    pages = [f"{body_buffer}\n\n## CHAPTER X"] * 6
    running = detect_running_headings(pages)
    # Even though the heading appears on every page, it's in the tail
    # zone (last 5 non-blank lines). It will be detected as a tail-
    # running heading. Verify head detection does NOT pick it up.
    head_running = [r for r in running if r.zone == "head"]
    assert head_running == []


def test_r4_normalization_handles_page_numbers():
    """`## Page 5: BASIC FANTASY RPG` and `## Page 12: BASIC FANTASY RPG`
    must normalize to the same key (R2's `_normalize` substitutes
    digits with `#`, which R4 reuses)."""
    pages = [
        _page_with_chrome_and_body(f"## Page {i}: BASIC FANTASY RPG")
        for i in range(1, 9)
    ]
    pages += ["No chrome.\n\nMore body."] * 2
    running = detect_running_headings(pages)
    head_running = [r for r in running if r.zone == "head"]
    assert len(head_running) == 1
    assert head_running[0].pages_seen == 8


def test_r4_does_not_touch_non_heading_lines():
    """A `**150 Spellcasting**` body bold (R2's structural-footer
    pattern) is not a heading — R4 must leave it alone."""
    pages = ["**150 Spellcasting**\n\nThe spellcaster casts."] * 8
    running = detect_running_headings(pages)
    assert running == []


def test_r4_strips_alongside_r2_in_clean_pages():
    """Both rules wired into clean_pages run on the same input
    without interference. Builds a fixture with running paragraph
    chrome (head/tail paragraphs) AND running heading chrome on the
    same pages.
    """
    pages = []
    for i in range(8):
        pages.append(
            f"## BASIC FANTASY RPG\n\n"
            f"Page {i + 1}\n\n"
            f"Body content for page {i + 1}.\n\n"
            f"More body for page {i + 1}.\n\n"
            f"Even more body for page {i + 1}.\n\n"
            f"Footer line that repeats."
        )
    cleaned, report = clean_pages(pages)
    assert report.headings_stripped >= 8
    assert report.paragraphs_stripped > 0
    assert all("BASIC FANTASY RPG" not in p for p in cleaned)


def test_r4_report_populates_headings_stripped_and_running_headings():
    pages = [_page_with_chrome_and_body("## CHROME")] * 8
    cleaned, report = clean_pages(pages)
    assert report.headings_stripped >= 8
    head_running = [r for r in report.running_headings if r.zone == "head"]
    assert len(head_running) == 1
    assert isinstance(head_running[0], RunningHeading)
    assert "R4 stripped=" in report.summary()


# ─────────────────────────── flattener compatibility ───────────────────────────


def test_flatten_br_works_on_r2_rejoined_output():
    """R2 re-joins paragraphs with \\n\\n. The flattener (line-based, splits
    on \\n) must still correctly expand <br>-packed table rows in the
    rejoined output. Locks in the whitespace-agnostic contract.
    """
    from server import _flatten_br_packed_cells

    pages = [_page(
        "Some prose.",
        "|Armor Class:<br>Hit Dice:|22<br>11|",
        "More prose.",
    )]
    cleaned, _ = clean_pages(pages)
    flattened = _flatten_br_packed_cells(cleaned[0])
    assert "|Armor Class:|22|" in flattened
    assert "|Hit Dice:|11|" in flattened

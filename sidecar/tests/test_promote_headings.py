"""Unit tests for the heading-hierarchy promotion module.

Pure function over (pages, spans_pages, toc) — no PDF, no IO. Pins the
contract that flat ``##`` headings get promoted to ``#``/``##``/``###``
based on per-document font histograms and (optionally) TOC entries.
"""

from legend_lore.promote_headings import (
    _rewrite_page_md,
    build_font_cluster_levels,
    build_toc_levels,
    collect_heading_signatures,
    is_junk_heading,
    promote_markdown,
)


def _spans(items):
    """Build a spans-page payload. items: [(text, size, bold), ...]"""
    return [
        {"text": t, "size": s, "bold": b}
        for t, s, b in items
    ]


def test_promote_empty_input():
    pages, report = promote_markdown([], [], {"entries": []}, strategy="font_cluster")
    assert pages == []
    assert report["n_headings"] == 0


def test_promote_unknown_strategy_raises():
    import pytest
    with pytest.raises(ValueError):
        promote_markdown([], [], {"entries": []}, strategy="bogus")


def test_font_cluster_promotes_three_clusters():
    """Three distinct (size, bold) clusters → modal stays at level 2,
    the larger cluster becomes level 1, the smaller becomes level 3.
    The larger cluster needs ≥ 2 rows to own level 1 — a singleton
    can't be the root — so there are two 24pt headings here.

    Heading words must be distinct across font sizes — the token-
    overlap signature matcher picks the largest-font matching span,
    so a token shared between sizes pollutes the smaller heading's
    signature.
    """
    md = (
        "## Foreword\n\nBody.\n\n"
        "## Prologue\n\nBody.\n\n"
        "## Spells\n\nBody.\n\n"
        "## Monsters\n\nBody.\n\n"
        "## Items\n\nBody.\n\n"
        "## Footnote\n\nBody."
    )
    pages = [{"page_number": 1, "markdown": md}]
    spans = [
        ("Foreword", 24.0, True),
        ("Prologue", 24.0, True),
        ("Spells", 18.0, True),
        ("Monsters", 18.0, True),
        ("Items", 18.0, True),
        ("Footnote", 12.0, True),
    ]
    spans_pages = [{"page_number": 1, "spans": _spans(spans)}]
    promoted, report = promote_markdown(
        pages, spans_pages, {"entries": []}, strategy="font_cluster"
    )
    out = promoted[0]["markdown"]
    assert "# Foreword" in out and "## Foreword" not in out
    assert "# Prologue" in out
    assert "## Spells" in out
    assert "## Monsters" in out
    assert "## Items" in out
    assert "### Footnote" in out
    assert report["promoted_level_distribution"][1] == 2
    assert report["promoted_level_distribution"][2] == 3
    assert report["promoted_level_distribution"][3] == 1


def test_font_cluster_modal_stays_at_level_two():
    """If every heading shares the same (size, bold) signature, the
    modal cluster level must be 2 — the chunker's natural section
    level. Single-cluster docs should round-trip unchanged."""
    md = "## Intro\n\nB.\n\n## Combat\n\nD.\n\n## Magic\n\nF."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("Intro", 18.0, True), ("Combat", 18.0, True), ("Magic", 18.0, True)]),
    }]
    promoted, _ = promote_markdown(
        pages, spans_pages, {"entries": []}, strategy="font_cluster"
    )
    out = promoted[0]["markdown"]
    assert "## Intro" in out
    assert "## Combat" in out
    assert "## Magic" in out


def test_toc_strategy_uses_toc_entry_depth():
    """When the TOC has a depth-1 entry that token-overlaps a heading
    on the same page, promote that heading to level 1. A second depth-1
    entry (unmatched here) makes depth 1 the effective top depth via the
    ≥ 2 rule, not the single-entry fallback."""
    md = "## Chapter One\n\nIntro."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("Chapter One", 18.0, True)]),
    }]
    toc = {"entries": [[1, "Chapter One", 1], [1, "Chapter Two", 20]]}
    promoted, _ = promote_markdown(pages, spans_pages, toc, strategy="toc")
    assert "# Chapter One" in promoted[0]["markdown"]


def test_toc_then_font_depth_two_falls_through_to_font():
    """TOC depth ≥ 2 entries are intentionally ignored under
    ``toc_then_font`` — they don't compose with the chunker's linear
    heading stack. Font cluster handles deeper levels."""
    md = "## Cloud Dragon Age Table\n\nTable rows.\n\n## Kraken\n\nMonster."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([
            ("Cloud Dragon Age Table", 14.0, True),
            ("Kraken", 14.0, True),
            ("Kraken", 14.0, True),
        ]),
    }]
    # Cloud Dragon Age Table is depth-2 in the TOC; under toc_then_font,
    # it must fall through to font_cluster (which puts both at modal
    # level 2 since they share a font signature). Two depth-1 entries
    # (unmatched here — they don't share a page with any row) pin the
    # effective top depth at 1, so the depth-2 entry stays relative
    # level 2, not the lone-depth-1 fallback that would make it "1".
    toc = {"entries": [[1, "Front Matter", 50], [1, "Appendix", 60],
                        [2, "Cloud Dragon Age Table", 1]]}
    promoted, report = promote_markdown(
        pages, spans_pages, toc, strategy="toc_then_font"
    )
    out = promoted[0]["markdown"]
    assert "## Cloud Dragon Age Table" in out
    assert "## Kraken" in out
    assert report["toc_used"] == 0


def test_toc_then_font_depth_one_takes_precedence():
    """A TOC depth-1 entry overrides the font signature — chapter
    titles should land at level 1 even when font analysis would
    place them differently. A second depth-1 entry (unmatched here)
    makes depth 1 the effective top depth via the ≥ 2 rule, not the
    single-entry fallback."""
    md = "## Part 6: Monsters\n\nIntro."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("Part 6: Monsters", 14.0, True)]),
    }]
    toc = {"entries": [[1, "Part 6: Monsters", 1], [1, "Part 7: Treasure", 30]]}
    promoted, report = promote_markdown(
        pages, spans_pages, toc, strategy="toc_then_font"
    )
    assert "# Part 6: Monsters" in promoted[0]["markdown"]
    assert report["toc_used"] == 1


def test_unmatched_signature_falls_back_conservatively():
    """When a heading's text has no token overlap with any page span
    (pymupdf4llm SRD heading-corruption: ``**Le endar Actions g y**``
    style), the heading must stay at its original level — never
    promoted nor demoted on a guess."""
    md = "## Legendary Actions\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    # No spans match — token-overlap returns no signature
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("totally unrelated text", 12.0, False)]),
    }]
    promoted, report = promote_markdown(
        pages, spans_pages, {"entries": []}, strategy="toc_then_font"
    )
    assert "## Legendary Actions" in promoted[0]["markdown"]
    assert report["fallback_count"] == 1
    assert report["n_unmatched_signature"] == 1


def test_cr_characters_in_body_lines_preserved():
    """Promotion splits/rejoins on `\\n` only. Bare `\\r` characters
    inside CR-fragmented prose lines must survive verbatim — R1
    downstream depends on them to detect and rejoin word-fragmented
    paragraphs."""
    md = "## Heading\n\nfirst \r  word \r  fragment\n\nMore."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("Heading", 18.0, True)]),
    }]
    promoted, _ = promote_markdown(
        pages, spans_pages, {"entries": []}, strategy="font_cluster"
    )
    assert "\r" in promoted[0]["markdown"]
    assert "first \r  word \r  fragment" in promoted[0]["markdown"]


def test_collect_heading_signatures_with_corrupted_text():
    """The spike's truncated-bold + char-reorder cases: token overlap
    of any length-≥2 lowercase token recovers the (size, bold) sig."""
    md = "## Le endar Actions g y\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        # Page has a "Legendary" token in its spans even though the
        # markdown heading text has it scrambled — token overlap on
        # "actions" still matches.
        "spans": _spans([("Legendary Actions", 12.0, True)]),
    }]
    rows = collect_heading_signatures(pages, spans_pages)
    assert len(rows) == 1
    assert rows[0]["sig"] == (12.0, True)


def test_build_font_cluster_levels_handles_no_rows():
    out = build_font_cluster_levels([])
    assert out["modal_sig"] is None
    assert out["level_by_sig"] == {}


def test_rows_are_sanitised_before_signatures():
    md = "# **S eed** **<u>p</u>**\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("Kraken", 13.9, True), ("Speed ", 9.8, True)])}]
    rows = collect_heading_signatures(pages, spans_pages)
    assert rows[0]["text"] == "Speed"
    assert rows[0]["parts"] == [("Speed", (9.8, True))]
    assert rows[0]["sig"] == (9.8, True)


def test_promote_rewrites_a_merged_line_as_two_headings():
    # The 18pt part needs a second row (added below as "# Dwarf") to keep
    # level 1 — a singleton signature can't be the root. That makes the
    # 18pt cluster 2 rows, so the 13.9pt cluster needs a third ("Orc
    # Traits", alongside "Elf Traits" and "Gnome Traits") to stay
    # strictly larger and keep the modal (level 2) slot. "Dwarf" is kept
    # out of every 13.9pt heading's text — a shared word across sizes
    # makes the token-overlap signature matcher pick the larger span for
    # both headings, mis-promoting the smaller one.
    md = ("# **Halfling Halflin Traits** **<u>g</u>**\n\nBody.\n\n## Elf Traits\n\nMore.\n\n"
          "## Gnome Traits\n\nMore.\n\n## Orc Traits\n\nEnd.\n\n# Dwarf\n\nBody.")
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([
        ("Halfling ", 18.0, True), ("Halfling Traits ", 13.9, True), ("Elf Traits", 13.9, True),
        ("Gnome Traits", 13.9, True), ("Orc Traits", 13.9, True), ("body", 9.8, False),
        ("Dwarf ", 18.0, True)])}]
    promoted, _ = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    lines = promoted[0]["markdown"].split("\n")
    assert lines[0] == "# Halfling"
    assert lines[1] == "## Halfling Traits"
    assert "## Elf Traits" in lines
    assert "# Dwarf" in lines


def test_promote_strips_markup_and_small_caps_from_every_heading():
    md = "## **chaRacteR RaceS**\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("chaRacteR RaceS", 11.0, True)])}]
    promoted, _ = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    assert promoted[0]["markdown"].split("\n")[0] == "## Character Races"


def test_junk_shapes():
    assert is_junk_heading("Armor Class 12 Hit Points 7 Speed 30")     # ≥ 2 numbers
    assert is_junk_heading("Table 3-1: Weapons")                        # caption
    assert is_junk_heading("Figure 2. The map")
    assert is_junk_heading("For free updates, errata and other OSRIC support, visit:")  # lead-in
    assert is_junk_heading("www.knights-n-knaves.com/osric")
    assert not is_junk_heading("Chapter 3")
    assert not is_junk_heading("Level 1 Spells")
    assert not is_junk_heading("THAC0")
    assert not is_junk_heading("Combat")
    assert is_junk_heading("This is a long sentence that explains at length what the reader is about to see next in the text")
    # OSRIC drop-cap letters (I, T, A) are promoted as headings and become
    # breadcrumb roots; a single alphabetic character is junk.
    assert is_junk_heading("I")
    assert is_junk_heading("T")
    # Die codes and module codes keep their digits — not junk by the
    # single-letter rule (stripped of non-word chars must be ONE letter).
    assert not is_junk_heading("d6")
    assert not is_junk_heading("B2")
    assert is_junk_heading("I.")


def test_junk_heading_is_demoted_to_bold_paragraph():
    md = "# Armor Class 12 Hit Points 7\n\nBody.\n\n## Combat\n\nMore."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("Armor Class 12 Hit Points 7", 9.8, True), ("Combat", 12.0, True)])}]
    promoted, report = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    lines = promoted[0]["markdown"].split("\n")
    assert lines[0] == "**Armor Class 12 Hit Points 7**"
    assert report["junk_demoted"] == 1


def test_sub_modal_signatures_get_distinct_levels():
    rows = [{"sig": (12.0, True)}] * 5 + [{"sig": (10.0, True)}] * 2 + [{"sig": (9.0, True)}] * 2 + [{"sig": (8.0, False)}]
    out = build_font_cluster_levels(rows)
    assert out["level_by_sig"] == {(12.0, True): 2, (10.0, True): 3, (9.0, True): 4, (8.0, False): 5}


def test_singleton_largest_signature_is_not_the_root():
    rows = [{"sig": (30.0, True)}] + [{"sig": (24.0, True)}] * 3 + [{"sig": (11.0, True)}] * 10
    out = build_font_cluster_levels(rows)
    assert out["level_by_sig"][(24.0, True)] == 1
    assert out["level_by_sig"][(30.0, True)] == 2
    assert out["level_by_sig"][(11.0, True)] == 2


def test_toc_effective_depth_shifts_when_depth_one_is_a_lone_book_title():
    rows = [
        {"page_number": 3, "line_idx": 0, "original_level": 1, "text": "Contributors", "sig": None},
        {"page_number": 15, "line_idx": 0, "original_level": 1, "text": "Combat", "sig": None},
    ]
    toc = [[1, "OSRIC", 1], [2, "Contributors", 3], [2, "Combat", 15], [3, "Initiative", 16]]
    out = build_toc_levels(rows, toc)
    assert out["effective_depth"] == 2
    assert out["level_by_row"] == {(3, 0): 1, (15, 0): 1}


def test_toc_effective_depth_is_one_when_depth_one_has_chapters():
    rows = [{"page_number": 5, "line_idx": 0, "original_level": 1, "text": "Combat", "sig": None}]
    toc = [[1, "Characters", 1], [1, "Combat", 5], [2, "Initiative", 6]]
    out = build_toc_levels(rows, toc)
    assert out["effective_depth"] == 1
    assert out["level_by_row"] == {(5, 0): 1}


def test_unmatched_heading_never_becomes_a_root():
    md = "# Zzqx\n\nBody.\n\n## Combat\n\nMore."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("Combat", 12.0, True), ("Grappling", 12.0, True)])}]
    promoted, report = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    assert promoted[0]["markdown"].split("\n")[0] == "## Zzqx"
    assert report["fallback_count"] == 1


def test_merged_line_junk_decided_per_part_first_junk_second_real():
    out = _rewrite_page_md(
        "# x\n\nBody.",
        [{"page_number": 1, "line_idx": 0, "original_level": 1,
          "text": "Armor Class 12 Hit Points 7",
          "parts": [("Armor Class 12 Hit Points 7", (9.8, True)), ("Kraken", (13.9, True))],
          "sig": (9.8, True), "junk": True}],
        {(1, 0): 2},
        {(13.9, True): 2},
    )
    lines = out.split("\n")
    assert lines[0] == "**Armor Class 12 Hit Points 7**"
    assert lines[1] == "## Kraken"


def test_merged_line_junk_decided_per_part_first_real_second_junk():
    out = _rewrite_page_md(
        "# x\n\nBody.",
        [{"page_number": 1, "line_idx": 0, "original_level": 1,
          "text": "Kraken",
          "parts": [("Kraken", (13.9, True)), ("Armor Class 12 Hit Points 7", (9.8, True))],
          "sig": (13.9, True), "junk": False}],
        {(1, 0): 2},
        {(9.8, True): 3},
    )
    lines = out.split("\n")
    assert lines[0] == "## Kraken"
    assert lines[1] == "**Armor Class 12 Hit Points 7**"

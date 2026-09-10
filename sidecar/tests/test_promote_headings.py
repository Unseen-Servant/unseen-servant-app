"""Unit tests for the heading-hierarchy promotion module.

Pure function over (pages, spans_pages, toc) — no PDF, no IO. Pins the
contract that flat ``##`` headings get promoted to ``#``/``##``/``###``
based on per-document font histograms and (optionally) TOC entries.
"""

from promote_headings import (
    build_font_cluster_levels,
    collect_heading_signatures,
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

    Heading words must be distinct across font sizes — the token-
    overlap signature matcher picks the largest-font matching span,
    so a token shared between sizes pollutes the smaller heading's
    signature.
    """
    md = (
        "## Foreword\n\nBody.\n\n"
        "## Spells\n\nBody.\n\n"
        "## Monsters\n\nBody.\n\n"
        "## Items\n\nBody.\n\n"
        "## Footnote\n\nBody."
    )
    pages = [{"page_number": 1, "markdown": md}]
    spans = [
        ("Foreword", 24.0, True),
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
    assert "## Spells" in out
    assert "## Monsters" in out
    assert "## Items" in out
    assert "### Footnote" in out
    assert report["promoted_level_distribution"][1] == 1
    assert report["promoted_level_distribution"][2] == 3
    assert report["promoted_level_distribution"][3] == 1


def test_font_cluster_modal_stays_at_level_two():
    """If every heading shares the same (size, bold) signature, the
    modal cluster level must be 2 — the chunker's natural section
    level. Single-cluster docs should round-trip unchanged."""
    md = "## A\n\nB.\n\n## C\n\nD.\n\n## E\n\nF."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("A", 18.0, True), ("C", 18.0, True), ("E", 18.0, True)]),
    }]
    promoted, _ = promote_markdown(
        pages, spans_pages, {"entries": []}, strategy="font_cluster"
    )
    out = promoted[0]["markdown"]
    assert "## A" in out
    assert "## C" in out
    assert "## E" in out


def test_toc_strategy_uses_toc_entry_depth():
    """When the TOC has a depth-1 entry that token-overlaps a heading
    on the same page, promote that heading to level 1."""
    md = "## Chapter One\n\nIntro."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("Chapter One", 18.0, True)]),
    }]
    toc = {"entries": [[1, "Chapter One", 1]]}
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
    # level 2 since they share a font signature).
    toc = {"entries": [[2, "Cloud Dragon Age Table", 1]]}
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
    place them differently."""
    md = "## Part 6: Monsters\n\nIntro."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": _spans([("Part 6: Monsters", 14.0, True)]),
    }]
    toc = {"entries": [[1, "Part 6: Monsters", 1]]}
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
    # Two 13.9pt rows make that signature the modal cluster (level 2); the
    # lone 18pt part is then the larger cluster and lands at level 1.
    md = "# **Halfling Halflin Traits** **<u>g</u>**\n\nBody.\n\n## Elf Traits\n\nMore.\n\n## Dwarf Traits\n\nEnd."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([
        ("Halfling ", 18.0, True), ("Halfling Traits ", 13.9, True), ("Elf Traits", 13.9, True),
        ("Dwarf Traits", 13.9, True), ("body", 9.8, False)])}]
    promoted, _ = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    lines = promoted[0]["markdown"].split("\n")
    assert lines[0] == "# Halfling"
    assert lines[1] == "## Halfling Traits"
    assert "## Elf Traits" in lines


def test_promote_strips_markup_and_small_caps_from_every_heading():
    md = "## **chaRacteR RaceS**\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("chaRacteR RaceS", 11.0, True)])}]
    promoted, _ = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    assert promoted[0]["markdown"].split("\n")[0] == "## Character Races"

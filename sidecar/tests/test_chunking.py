"""Unit tests for the structure-aware chunker.

Pure function over `list[PageMarkdown]` — no PDF, no Chroma, no Ollama.
Mirrors the boundary rules validated by the chunker spike (see
sidecar/chunker.py docstring for the FINDINGS link).
"""

from chunker import (
    CHUNKER_VERSION,
    HARD_CAP,
    Chunk,
    PageMarkdown,
    structure_aware,
)


def _page(n: int, md: str) -> PageMarkdown:
    return PageMarkdown(page_number=n, markdown=md)


def test_empty_input_returns_empty_list():
    assert structure_aware([], source_pdf="x.pdf") == []


def test_pure_prose_under_soft_cap_is_one_chunk():
    md = "First paragraph.\n\nSecond paragraph."
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "prose"
    assert "First paragraph" in chunks[0].text
    assert "Second paragraph" in chunks[0].text
    assert chunks[0].section_heading is None


def test_heading_starts_new_chunk_even_when_buffer_small():
    md = "Tiny intro paragraph.\n\n## Combat\n\nCombat rules go here."
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    assert len(chunks) == 2
    assert chunks[0].section_heading is None
    assert "Tiny intro" in chunks[0].text
    assert chunks[1].section_heading == "Combat"
    assert "Combat rules" in chunks[1].text


def test_heading_stack_pops_to_correct_level():
    md = (
        "## Monsters\n\nIntro to monsters.\n\n"
        "### Dragons\n\nDragon overview.\n\n"
        "#### Cloud Dragon\n\nCloud dragon details.\n\n"
        "### Goblins\n\nGoblin overview."
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    breadcrumbs = [c.section_heading for c in chunks if c.chunk_type == "prose"]
    assert "Monsters" in breadcrumbs
    assert "Monsters > Dragons" in breadcrumbs
    assert "Monsters > Dragons > Cloud Dragon" in breadcrumbs
    assert "Monsters > Goblins" in breadcrumbs


def test_pipe_table_emitted_atomically():
    md = (
        "## Cloud Dragon\n\n"
        "| Armor Class: | 22 |\n"
        "| Hit Dice: | 11 |\n"
        "| Movement: | 30' Fly 80' |\n"
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1
    assert "Armor Class" in table_chunks[0].text
    assert "Hit Dice" in table_chunks[0].text
    assert "Movement" in table_chunks[0].text
    assert table_chunks[0].section_heading == "Cloud Dragon"


def test_table_breaks_prose_buffer():
    md = (
        "## Section\n\n"
        "Some prose before the table.\n\n"
        "| col1 | col2 |\n| a | b |\n\n"
        "Some prose after the table."
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    types = [c.chunk_type for c in chunks]
    assert types == ["prose", "table", "prose"]


def test_soft_cap_splits_long_prose_at_paragraph_boundary():
    para = "x" * 600
    md = f"## Lore\n\n{para}\n\n{para}\n\n{para}"
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf", soft_cap=1000)
    prose = [c for c in chunks if c.chunk_type == "prose"]
    assert len(prose) >= 2
    for c in prose:
        # Splits happen at \n\n boundaries, never mid-paragraph.
        assert not c.text.strip().endswith("x" * 600 + "x")


def test_oversized_paragraph_emitted_whole():
    big = "y" * 2500
    md = f"## Lore\n\n{big}"
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf", soft_cap=1000)
    prose = [c for c in chunks if c.chunk_type == "prose"]
    assert len(prose) == 1
    assert len(prose[0].text) >= 2500


def test_hard_cap_splits_oversized_chunks():
    huge_para = "z" * (HARD_CAP + 5000)
    md = f"## Lore\n\n{huge_para}"
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    for c in chunks:
        assert len(c.text) <= HARD_CAP


def test_ordinals_are_sequential():
    md = (
        "## A\n\nProse A.\n\n"
        "| col1 | col2 |\n| 1 | 2 |\n\n"
        "## B\n\nProse B."
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunk_metadata_fields_populated():
    md = "## Heading\n\nSome content here."
    chunks = structure_aware([_page(7, md)], source_pdf="my.pdf")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.text
    assert c.page_start == 7
    assert c.page_end == 7
    assert c.chunk_type == "prose"
    assert c.section_heading == "Heading"
    assert c.source_pdf == "my.pdf"
    assert c.chunker == CHUNKER_VERSION
    assert c.ordinal == 0


def test_multi_page_input_tracks_page_range():
    pages = [
        _page(1, "## Section\n\nPart one prose."),
        _page(2, "Part two prose, same section."),
    ]
    chunks = structure_aware(pages, source_pdf="x.pdf")
    prose = [c for c in chunks if c.chunk_type == "prose"]
    assert len(prose) == 1
    assert prose[0].page_start == 1
    assert prose[0].page_end == 2


def test_table_spanning_pages_stays_atomic_within_page():
    """Tables don't merge across pages — each page's table block emits separately.

    This matches what pymupdf4llm produces: tables on page boundaries arrive
    as two separate pipe-row runs, one per page. Atomicity is per-page.
    """
    pages = [
        _page(1, "| a | b |\n| 1 | 2 |"),
        _page(2, "| c | d |\n| 3 | 4 |"),
    ]
    chunks = structure_aware(pages, source_pdf="x.pdf")
    tables = [c for c in chunks if c.chunk_type == "table"]
    assert len(tables) == 2
    assert tables[0].page_start == 1 and tables[0].page_end == 1
    assert tables[1].page_start == 2 and tables[1].page_end == 2


def test_page_marker_lines_are_skipped():
    md = "<!-- page 5 -->\n## Heading\n\nBody text."
    chunks = structure_aware([_page(5, md)], source_pdf="x.pdf")
    assert all("<!-- page" not in c.text for c in chunks)


def test_chunks_before_first_heading_have_no_breadcrumb():
    md = "Front matter prose with no preceding heading."
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    assert len(chunks) == 1
    assert chunks[0].section_heading is None


# ─────────────────── stat-block sub-section exemptions ───────────────────


def test_actions_subheading_does_not_break_monster_chunk():
    """`## Actions` after `## Goblin` must stay anchored to the Goblin
    breadcrumb so searches for "Goblin attack bonus" surface a parent
    that contains both the description and the attack list."""
    md = (
        "## Goblin\n\nA cowardly humanoid raider.\n\n"
        "## Actions\n\n"
        "Scimitar. Melee Weapon Attack: +4 to hit.\n\n"
        "Shortbow. Ranged Weapon Attack: +4 to hit."
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    assert all(c.section_heading == "Goblin" for c in chunks)
    body = "\n\n".join(c.text for c in chunks)
    assert "cowardly humanoid raider" in body
    assert "Scimitar" in body
    assert "Shortbow" in body


def test_bold_wrapped_actions_heading_also_exempt():
    """Black-Flag's pymupdf4llm output renders the heading as
    `## **ACTIONS**` — the same exemption applies after stripping
    bold + lowercasing."""
    md = (
        "## Goblin\n\nThe goblin.\n\n"
        "## **ACTIONS**\n\nAttack details."
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    assert all(c.section_heading == "Goblin" for c in chunks)


def test_each_exempt_label_is_non_breaking():
    """Spot-check the full default set so a future maintainer who
    adds/removes a label sees a clear failure if behavior shifts."""
    for label in [
        "Actions", "Bonus Actions", "Reactions", "Legendary Actions",
        "Lair Actions", "Mythic Actions", "Villain Actions",
        "Traits", "Special Traits", "Spellcasting", "Innate Spellcasting",
        "Equipment",
    ]:
        md = f"## Monster\n\nDescription.\n\n## {label}\n\nDetails."
        chunks = structure_aware([_page(1, md)], source_pdf=f"{label}.pdf")
        assert all(c.section_heading == "Monster" for c in chunks), (
            f"`## {label}` unexpectedly broke the parent chunk"
        )


def test_real_heading_after_exempt_subsection_still_breaks():
    """An exemption keeps the parent breadcrumb but the next real
    heading must still pop and start a new chunk normally."""
    md = (
        "## Goblin\n\nDesc.\n\n"
        "## Actions\n\nAttack.\n\n"
        "## Hobgoblin\n\nNext monster."
    )
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    breadcrumbs = {c.section_heading for c in chunks}
    assert "Goblin" in breadcrumbs
    assert "Hobgoblin" in breadcrumbs
    # "Actions" itself must NOT appear as a breadcrumb.
    assert "Actions" not in breadcrumbs


def test_non_exempt_heading_still_breaks_normally():
    """Sanity: a heading that's NOT in the exemption set must still
    cause a chunk break (regression guard for the exemption logic)."""
    md = "## Combat\n\nIntro.\n\n## Damage\n\nDamage rules."
    chunks = structure_aware([_page(1, md)], source_pdf="x.pdf")
    breadcrumbs = [c.section_heading for c in chunks]
    assert "Combat" in breadcrumbs
    assert "Damage" in breadcrumbs

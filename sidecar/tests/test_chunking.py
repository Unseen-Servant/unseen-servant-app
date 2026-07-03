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
    _enforce_hard_cap,
    structure_aware,
)
from promote_headings import promote_markdown


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


# ─────────────────────── hard-cap enforcement ───────────────────────


def test_hard_cap_falls_back_to_single_newline_for_tables():
    """Table text has no \\n\\n boundaries (rows joined by \\n). The cap
    splitter must cut on a row boundary, not mid-row at exactly HARD_CAP."""
    row = "|" + "x" * 96 + "|yy|"
    table = "\n".join(row for _ in range(250))  # ~25k chars, no \n\n anywhere
    chunk = Chunk(
        text=table, page_start=1, page_end=1, chunk_type="table",
        section_heading="Big Table", source_pdf="test.pdf",
        chunker="structure_aware-v2", ordinal=0,
    )
    out = _enforce_hard_cap([chunk], HARD_CAP)
    assert len(out) >= 2
    for c in out:
        assert len(c.text) <= HARD_CAP
        for line in c.text.splitlines():
            assert line.startswith("|") and line.endswith("|")  # no mid-row cut


# ─────────────────── promotion → chunker integration ───────────────────


def test_promotion_anchors_stat_block_subsection_to_parent():
    """Stat-block sub-sections (Actions, Legendary Actions, …) lose
    their parent monster breadcrumb when emitted as flat ``##``. With
    heading-hierarchy promotion (issue #157), a font-size hierarchy
    on the page promotes the parent monster to ``##`` and the
    sub-section to ``###``, so the chunker's heading stack keeps the
    monster in scope.

    This test replaces the PR #155 hardcoded-exemption mechanism
    tests: behavior preserved (sub-section anchored to parent)
    via a different, scaling mechanism (font-cluster promotion).

    Fixture mirrors a multi-monster stat-block page: one chapter-
    title heading at the largest font, multiple monster-name
    headings at the modal font (so they constitute the modal
    cluster), and per-monster sub-section headings at the smaller
    font.
    """
    md = (
        "## Monsters\n\nThe creatures of the world.\n\n"
        "## Solar\n\nA solar is a celestial of unmatched might.\n\n"
        "## Legendary Actions\n\n"
        "The solar can take 3 legendary actions per round.\n\n"
        "## Kraken\n\nA kraken is a sea behemoth.\n\n"
        "## Legendary Actions\n\nThe kraken can submerge.\n\n"
        "## Lich\n\nA lich is an undead spellcaster."
    )
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{
        "page_number": 1,
        "spans": [
            # Monsters at the largest font → level 1 (chapter title)
            {"text": "Monsters", "size": 24.0, "bold": True},
            # Three monster names at the modal font (count = 3) → level 2
            {"text": "Solar", "size": 18.0, "bold": True},
            {"text": "Kraken", "size": 18.0, "bold": True},
            {"text": "Lich", "size": 18.0, "bold": True},
            # Two sub-section labels at smaller font (count = 2) → level 3
            {"text": "Legendary Actions", "size": 12.0, "bold": True},
            {"text": "Legendary Actions", "size": 12.0, "bold": True},
        ],
    }]
    toc = {"entries": []}
    promoted, _report = promote_markdown(
        pages, spans_pages, toc, strategy="toc_then_font"
    )
    chunks = structure_aware(
        [PageMarkdown(page_number=1, markdown=promoted[0]["markdown"])],
        source_pdf="srd.pdf",
    )
    solar_la_chunk = next(
        c for c in chunks if "3 legendary actions per round" in c.text
    )
    assert solar_la_chunk.section_heading is not None
    assert "Monsters" in solar_la_chunk.section_heading
    assert "Solar" in solar_la_chunk.section_heading
    # Sanity: the Kraken sub-section should anchor to Kraken, not Solar.
    kraken_la_chunk = next(
        c for c in chunks if "kraken can submerge" in c.text
    )
    assert "Kraken" in kraken_la_chunk.section_heading
    assert "Solar" not in kraken_la_chunk.section_heading

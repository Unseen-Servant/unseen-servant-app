"""Unit tests for granularity — parent-doc retrieval indexer.

Validated end-to-end in chunk_granularity_spike (sibling experiments
repo). These tests pin the contract:
  - contiguous-run grouping (not group-by-breadcrumb-globally)
  - tables atomic
  - prose sub-split paragraph-aware
  - 6,000-char parent cap forces sub-parents
  - orphan / no-heading chunks each get their own parent
  - per-chunk page provenance preserved on parents (min/max)
"""

from chunker import Chunk
from granularity import (
    EmbedUnit,
    ParentDoc,
    PARENT_HARD_CAP,
    SMALL_TARGET,
    build,
    _split_prose,
    _group_into_parents,
)


def _chunk(
    text: str, heading: str | None, ordinal: int,
    chunk_type: str = "prose",
    page_start: int = 1, page_end: int = 1,
) -> Chunk:
    return Chunk(
        text=text,
        page_start=page_start,
        page_end=page_end,
        chunk_type=chunk_type,
        section_heading=heading,
        source_pdf="test.pdf",
        chunker="structure_aware-v2",
        ordinal=ordinal,
    )


# ─────────────────────── _split_prose ───────────────────────


def test_split_prose_empty_input():
    assert _split_prose("") == []


def test_split_prose_short_text_is_one_unit():
    """Anything shorter than SMALL_TARGET stays whole."""
    text = "A short paragraph."
    assert _split_prose(text) == [text]


def test_split_prose_paragraph_boundaries():
    """Splits prefer \\n\\n boundaries when possible."""
    paras = ["Paragraph " + ("x " * 100) for _ in range(3)]
    text = "\n\n".join(paras)
    out = _split_prose(text)
    assert len(out) >= 2
    for unit in out:
        assert "Paragraph" in unit


def test_split_prose_long_paragraph_falls_back_to_sentences():
    """A single paragraph longer than SMALL_HARD splits on sentence boundaries."""
    long_para = " ".join([f"Sentence number {i} appears here." for i in range(50)])
    out = _split_prose(long_para)
    assert len(out) > 1
    for unit in out:
        assert len(unit) <= 1200  # very loose upper bound; sentences ~30 chars


# ─────────────────────── _group_into_parents ───────────────────────


def test_group_contiguous_same_breadcrumb():
    """Adjacent chunks sharing a breadcrumb merge into one parent."""
    chunks = [
        _chunk("A", "Goblin", 0),
        _chunk("B", "Goblin", 1),
        _chunk("C", "Goblin", 2),
    ]
    groups = _group_into_parents(chunks)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_group_breadcrumb_change_starts_new_parent():
    chunks = [
        _chunk("A", "Goblin", 0),
        _chunk("B", "Goblin", 1),
        _chunk("C", "Hobgoblin", 2),
        _chunk("D", "Hobgoblin", 3),
    ]
    groups = _group_into_parents(chunks)
    assert len(groups) == 2
    assert {g[0].section_heading for g in groups} == {"Goblin", "Hobgoblin"}


def test_group_same_breadcrumb_non_adjacent_separate_parents():
    """Critical case: pymupdf4llm's `## **ACTIONS**` repeats across monster
    cards. Naive group-by-breadcrumb would collapse them; contiguous-run
    keeps each card separate."""
    chunks = [
        _chunk("A", "ACTIONS", 0),
        _chunk("B", "Goblin Stats", 1),
        _chunk("C", "ACTIONS", 2),
        _chunk("D", "Hobgoblin Stats", 3),
        _chunk("E", "ACTIONS", 4),
    ]
    groups = _group_into_parents(chunks)
    # ACTIONS appears 3 times but each is its own parent (5 groups total).
    assert len(groups) == 5


def test_group_cap_overflow_starts_sub_parent():
    """A single contiguous breadcrumb with too-much text splits at the cap."""
    big_text = "x" * (PARENT_HARD_CAP // 2 + 1)
    chunks = [_chunk(big_text, "BigSection", i) for i in range(3)]
    groups = _group_into_parents(chunks)
    assert len(groups) >= 2  # the third chunk would push beyond cap


def test_group_orphan_chunks_each_own_parent():
    """Chunks with section_heading=None are still grouped while contiguous,
    but a None breadcrumb is distinct from any real heading."""
    chunks = [
        _chunk("A", None, 0),
        _chunk("B", None, 1),
        _chunk("C", "Heading", 2),
    ]
    groups = _group_into_parents(chunks)
    assert len(groups) == 2
    assert groups[0][0].section_heading is None
    assert groups[1][0].section_heading == "Heading"


# ─────────────────────── build (full pipeline) ───────────────────────


def test_build_emits_embed_units_and_parents():
    chunks = [
        _chunk("Goblin prose paragraph.", "Goblin", 0),
        _chunk("|stat|val|\n|---|---|\n|HD|1-1|", "Goblin", 1, chunk_type="table"),
    ]
    embed_units, parents = build(chunks)
    assert len(parents) == 1
    parent = parents[0]
    assert parent.chunk_type == "mixed"
    assert "Goblin prose paragraph." in parent.text
    assert "|stat|val|" in parent.text
    assert all(eu.parent_id == parent.parent_id for eu in embed_units)


def test_build_tables_linearized_to_rows():
    """Table chunks emit one embed unit per row (#144), all sharing the
    same parent_id and carrying chunk_type='table'."""
    table = "|a|b|c|\n|---|---|---|\n" + "\n".join(
        f"|{i}|{i*2}|{i*3}|" for i in range(20)
    )
    chunks = [_chunk(table, "Stats", 0, chunk_type="table")]
    embed_units, parents = build(chunks)
    assert len(embed_units) == 20
    assert all(eu.chunk_type == "table" for eu in embed_units)
    assert all(eu.parent_id == parents[0].parent_id for eu in embed_units)
    # Row sentence shape: "a: 0; b: 0; c: 0", "a: 1; b: 2; c: 3", ...
    assert embed_units[0].text == "a: 0; b: 0; c: 0"
    assert embed_units[1].text == "a: 1; b: 2; c: 3"


def test_build_table_fallback_when_unparseable():
    """A chunk tagged as 'table' but with no pipe characters falls back
    to a single atomic embed unit carrying the original text."""
    not_a_table = "Just some prose that got mis-tagged as a table."
    chunks = [_chunk(not_a_table, "Section", 0, chunk_type="table")]
    embed_units, _ = build(chunks)
    assert len(embed_units) == 1
    assert embed_units[0].text == not_a_table
    assert embed_units[0].chunk_type == "table"


def test_build_table_parent_text_preserved():
    """Load-bearing invariant: the original markdown table is in parent.text
    so the LLM still receives the full atomic table at retrieval, even
    though embed units are per-row."""
    table = "|a|b|c|\n|---|---|---|\n|1|2|3|\n|4|5|6|"
    chunks = [_chunk(table, "Stats", 0, chunk_type="table")]
    _, parents = build(chunks)
    assert len(parents) == 1
    assert table in parents[0].text


def test_build_prose_sub_split():
    """A long prose chunk produces multiple embed units."""
    long_prose = "\n\n".join(
        f"Paragraph {i}. " + ("filler " * 40) for i in range(8)
    )
    chunks = [_chunk(long_prose, "Lore", 0)]
    embed_units, _ = build(chunks)
    assert len(embed_units) > 1
    assert all(eu.parent_id == embed_units[0].parent_id for eu in embed_units)


def test_build_parent_page_span_min_max():
    """Parent.page_start = min, page_end = max across the contiguous run."""
    chunks = [
        _chunk("A", "Section", 0, page_start=10, page_end=10),
        _chunk("B", "Section", 1, page_start=11, page_end=12),
        _chunk("C", "Section", 2, page_start=12, page_end=13),
    ]
    _, parents = build(chunks)
    assert len(parents) == 1
    assert parents[0].page_start == 10
    assert parents[0].page_end == 13


def test_build_parent_id_stable_for_same_input():
    chunks = [_chunk("A", "S", 0), _chunk("B", "S", 1)]
    _, p1 = build(chunks)
    _, p2 = build(chunks)
    assert p1[0].parent_id == p2[0].parent_id


def test_build_parent_id_disambiguates_repeated_heading():
    chunks = [
        _chunk("A", "ACTIONS", 0),
        _chunk("B", "Goblin", 1),
        _chunk("C", "ACTIONS", 2),
    ]
    _, parents = build(chunks)
    actions_parents = [p for p in parents if p.section_heading == "ACTIONS"]
    assert len(actions_parents) == 2
    assert actions_parents[0].parent_id != actions_parents[1].parent_id


def test_build_empty_input():
    embed_units, parents = build([])
    assert embed_units == []
    assert parents == []

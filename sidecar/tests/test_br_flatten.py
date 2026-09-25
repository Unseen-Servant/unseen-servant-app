"""
Unit tests for _flatten_br_packed_cells().

Why test this separately?
- It's a pure string-in/string-out function: deterministic, no IO.
- It's the only piece of PDF-extraction post-processing we own; bugs here
  corrupt every indexed chunk.
- Guards against over-application on legitimate multi-line cells.

Covers the pymupdf4llm spike finding: stat-block tables emit
`|Armor Class:<br>Hit Dice:|22<br>11|` when a single visual cell spans
multiple logical rows. When <br> counts match across cells, we expand to
one row per pair. When they don't, we leave the row alone.
"""

from legend_lore.service import _flatten_br_packed_cells


def test_empty_input():
    assert _flatten_br_packed_cells("") == ""


def test_non_table_lines_untouched():
    md = "# Heading\n\nSome prose with **bold** and <br> tags inline.\n"
    assert _flatten_br_packed_cells(md) == md


def test_header_separator_passes_through():
    """Markdown header separators (|---|---|) have zero <br>s — leave alone."""
    line = "|---|---|"
    assert _flatten_br_packed_cells(line) == line


def test_bfrpg_stat_block_example():
    """Spike's canonical example: matched 1-<br> counts split into two rows."""
    row = "|Armor Class:<br>Hit Dice:|22<br>11|"
    expected = "|Armor Class:|22|\n|Hit Dice:|11|"
    assert _flatten_br_packed_cells(row) == expected


def test_trailing_empty_column_preserved():
    """Row with a zero-<br> empty trailing cell — repeat the empty cell per split row."""
    row = "|Armor Class:<br>Hit Dice:|22<br>11**(+9)||"
    expected = "|Armor Class:|22||\n|Hit Dice:|11**(+9)||"
    assert _flatten_br_packed_cells(row) == expected


def test_four_row_stat_block():
    """Three-<br> pack expands into four rows."""
    row = "|Movement:<br>No. Appearing:<br>Save As:<br>Morale:|30'<br>1d4<br>Fighter 11<br>10|"
    expected = (
        "|Movement:|30'|\n"
        "|No. Appearing:|1d4|\n"
        "|Save As:|Fighter 11|\n"
        "|Morale:|10|"
    )
    assert _flatten_br_packed_cells(row) == expected


def test_unmatched_counts_preserved():
    """Mismatched <br> counts = legitimate multi-line content; do not split."""
    row = "|foo<br>bar|baz|"
    assert _flatten_br_packed_cells(row) == row


def test_single_cell_with_br_preserved():
    """Only one cell has a <br> — not a packed pattern; leave alone."""
    row = "|note: see page 12<br>for details|see also|"
    assert _flatten_br_packed_cells(row) == row


def test_br_variants_case_and_self_closing():
    """Handle <BR>, <br/>, <br /> the same as <br>."""
    row = "|A<BR>B|X<br/>Y|"
    expected = "|A|X|\n|B|Y|"
    assert _flatten_br_packed_cells(row) == expected


def test_three_cells_all_packed():
    """All three cells packed with matching counts split across all three."""
    row = "|a<br>b|c<br>d|e<br>f|"
    expected = "|a|c|e|\n|b|d|f|"
    assert _flatten_br_packed_cells(row) == expected


def test_mixed_document():
    """Prose, heading, packed row, non-packed row — only packed row splits."""
    md = (
        "# Cloud Dragon\n"
        "\n"
        "A fearsome beast.\n"
        "\n"
        "|Armor Class:<br>Hit Dice:|22<br>11|\n"
        "|Notes|stays as one row|\n"
        "\n"
        "More prose."
    )
    expected = (
        "# Cloud Dragon\n"
        "\n"
        "A fearsome beast.\n"
        "\n"
        "|Armor Class:|22|\n"
        "|Hit Dice:|11|\n"
        "|Notes|stays as one row|\n"
        "\n"
        "More prose."
    )
    assert _flatten_br_packed_cells(md) == expected


def test_leading_whitespace_row_still_detected():
    """Rows indented by table-rendering quirks still match."""
    row = "  |A<br>B|1<br>2|"
    out = _flatten_br_packed_cells(row)
    assert "|A|1|" in out
    assert "|B|2|" in out

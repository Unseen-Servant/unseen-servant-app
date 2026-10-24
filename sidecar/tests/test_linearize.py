"""Unit tests for linearize — pipe-table row-as-sentence linearizer.

Ported behavior is pinned against the table_retrieval_spike's verified
cases (see FINDINGS.md in the spikes repo), most importantly the
title-row heuristic that the spike found load-bearing on BFRPG tables.
"""

from legend_lore.linearize import coverage_ratio, linearize_table


STANDARD_TABLE = (
    "|**Armor Type**|**Price**|**Weight**|**AC**|\n"
    "|---|---|---|---|\n"
    "|Leather Armor|20gp|15|13|\n"
    "|Chain Mail|60gp|40|15|"
)

# BFRPG armor-table layout: single-cell title row BEFORE the separator,
# real header AFTER it. The spike's first-pass parser broke on this.
TITLE_ROW_TABLE = (
    "|Armor and Shields||||\n"
    "|---|---|---|---|\n"
    "|**Armor Type**|**Price**|**Weight**|**AC**|\n"
    "|Chain Mail|60gp|40|15|"
)


def test_standard_table_rows():
    header, sentences = linearize_table(STANDARD_TABLE)
    assert header == ["Armor Type", "Price", "Weight", "AC"]
    assert sentences == [
        "Armor Type: Leather Armor; Price: 20gp; Weight: 15; AC: 13",
        "Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15",
    ]


def test_title_row_demoted_to_use_real_header():
    """The spike's golden case: title row must not be mistaken for the
    header, or Price/Weight/AC are silently dropped."""
    header, sentences = linearize_table(TITLE_ROW_TABLE)
    assert sentences == [
        "Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15",
    ]


def test_no_separator_first_row_is_header():
    table = "|Thief Level|Open Locks|\n|3|35|\n|4|40|"
    header, sentences = linearize_table(table)
    assert header == ["Thief Level", "Open Locks"]
    assert sentences == [
        "Thief Level: 3; Open Locks: 35",
        "Thief Level: 4; Open Locks: 40",
    ]


def test_partially_empty_header_gets_positional_names():
    table = "|Name||AC|\n|---|---|---|\n|Goblin|small|14|"
    header, sentences = linearize_table(table)
    assert header == ["Name", "col2", "AC"]
    assert sentences == ["Name: Goblin; col2: small; AC: 14"]


def test_empty_cells_skipped_in_sentences():
    table = "|a|b|c|\n|---|---|---|\n|1||3|"
    _, sentences = linearize_table(table)
    assert sentences == ["a: 1; c: 3"]


def test_rows_padded_and_truncated_to_header_width():
    table = "|a|b|\n|---|---|\n|1|\n|2|3|4|"
    _, sentences = linearize_table(table)
    assert sentences == ["a: 1", "a: 2; b: 3"]


def test_br_in_cell_flattened_to_space():
    table = "|a|b|\n|---|---|\n|one<br>two|3|"
    _, sentences = linearize_table(table)
    assert sentences == ["a: one two; b: 3"]


def test_non_table_text_returns_empty():
    assert linearize_table("Just a paragraph of prose, no pipes here.") == ([], [])


def test_empty_input_returns_empty():
    assert linearize_table("") == ([], [])


def test_coverage_high_for_clean_parse():
    header, sentences = linearize_table(STANDARD_TABLE)
    assert coverage_ratio(STANDARD_TABLE, header, sentences) >= 0.6


def test_coverage_high_for_title_row_table():
    header, sentences = linearize_table(TITLE_ROW_TABLE)
    assert coverage_ratio(TITLE_ROW_TABLE, header, sentences) >= 0.6


def test_coverage_low_when_narrow_header_drops_columns():
    """A 2-cell header over 5-cell data rows: _parse_table truncates each
    row to 2 cells, silently dropping 3 columns. The ratio must expose
    this so build() can fall back to the atomic unit."""
    wide_cell = "x" * 20
    rows = "\n".join(
        f"|{wide_cell}|{wide_cell}|{wide_cell}|{wide_cell}|{wide_cell}|"
        for _ in range(5)
    )
    table = "|Wide|Table|\n|---|---|\n" + rows
    header, sentences = linearize_table(table)
    assert sentences  # parse "succeeds"...
    assert coverage_ratio(table, header, sentences) < 0.6  # ...but lossily


def test_coverage_zero_for_no_sentences():
    assert coverage_ratio("no table here", [], []) == 0.0


def test_coverage_high_for_long_title_single_row_table():
    """A long descriptive title row must not drag a lossless 1-row parse
    below the threshold (title content is legitimately absent from the
    sentences)."""
    table = (
        "|Cost to Hire Retainers and Specialists by Class and Level||||\n"
        "|---|---|---|---|\n"
        "|**Class**|**Level**|**Cost**|**Notes**|\n"
        "|Fighter|3|100gp|per month|"
    )
    header, sentences = linearize_table(table)
    assert sentences
    assert coverage_ratio(table, header, sentences) >= 0.6


def test_coverage_high_for_sparse_table():
    """Empty cells contribute nothing to either side of the ratio — a
    sparse-but-valid table must pass."""
    table = "|a|b|c|d|\n|---|---|---|---|\n|1|||4|\n||2||#|"
    header, sentences = linearize_table(table)
    assert coverage_ratio(table, header, sentences) >= 0.6


def test_coverage_passes_when_dropped_cells_are_short():
    """Truncating short-code columns loses little token mass — the guard
    correctly lets it through (boundary of its discrimination)."""
    table = "|k1|k2|\n|---|---|\n" + "\n".join("|ab|cd|ef|gh|ij|" for _ in range(5))
    header, sentences = linearize_table(table)
    assert coverage_ratio(table, header, sentences) >= 0.6

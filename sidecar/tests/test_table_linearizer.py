"""Unit tests for the pipe-table linearizer (#144).

Pins:
  - simple table → one row sentence per data row
  - BFRPG title-row demotion: single-cell title before separator → real
    header is the first post-separator row (load-bearing for chain mail)
  - <br>/\\n inside cells flatten to spaces
  - empty cells are skipped per-cell (no "h: " stub)
  - empty / whitespace-only rows dropped
  - no-separator tables: first row taken as header
  - non-pipe content returns ([], []) so granularity can fall back
"""

from table_linearizer import linearize_table


def test_simple_table_three_rows():
    text = (
        "| Name | HP | AC |\n"
        "|---|---|---|\n"
        "| Goblin | 7 | 13 |\n"
        "| Orc | 15 | 14 |\n"
        "| Troll | 84 | 16 |\n"
    )
    header, rows = linearize_table(text)
    assert header == ["Name", "HP", "AC"]
    assert rows == [
        "Name: Goblin; HP: 7; AC: 13",
        "Name: Orc; HP: 15; AC: 14",
        "Name: Troll; HP: 84; AC: 16",
    ]


def test_bfrpg_title_row_demotion():
    """Single-cell title row before the separator → real header lives
    AFTER the separator (the BFRPG armor / weapons family).

    This is the chain-mail-at-p15 case from the spike: the real header
    must be picked up post-separator so 'Armor Type: Chain Mail; ...'
    is emitted, not 'Armor and Shields: Chain Mail; ...'.
    """
    text = (
        "| **Armor and Shields** |\n"
        "|---|\n"
        "| Armor Type | Price | Weight | AC |\n"
        "| Leather | 20 | 15 | 12 |\n"
        "| Chain Mail | 60 | 40 | 15 |\n"
        "| Plate | 450 | 50 | 17 |\n"
    )
    header, rows = linearize_table(text)
    assert header == ["Armor Type", "Price", "Weight", "AC"]
    assert rows == [
        "Armor Type: Leather; Price: 20; Weight: 15; AC: 12",
        "Armor Type: Chain Mail; Price: 60; Weight: 40; AC: 15",
        "Armor Type: Plate; Price: 450; Weight: 50; AC: 17",
    ]


def test_br_in_cells_flattens_to_space():
    text = (
        "| Name | Notes |\n"
        "|---|---|\n"
        "| Goblin | small<br>cowardly |\n"
    )
    header, rows = linearize_table(text)
    assert header == ["Name", "Notes"]
    assert rows == ["Name: Goblin; Notes: small cowardly"]


def test_empty_cells_skipped_per_cell():
    """An empty cell yields no "h: " token in the row sentence."""
    text = (
        "| Name | HP | AC |\n"
        "|---|---|---|\n"
        "| Goblin |  | 13 |\n"
    )
    _, rows = linearize_table(text)
    assert rows == ["Name: Goblin; AC: 13"]


def test_empty_rows_dropped():
    text = (
        "| Name | HP |\n"
        "|---|---|\n"
        "| Goblin | 7 |\n"
        "|  |  |\n"
        "| Orc | 15 |\n"
    )
    _, rows = linearize_table(text)
    assert rows == ["Name: Goblin; HP: 7", "Name: Orc; HP: 15"]


def test_no_separator_first_row_is_header():
    text = (
        "| Name | HP |\n"
        "| Goblin | 7 |\n"
        "| Orc | 15 |\n"
    )
    header, rows = linearize_table(text)
    assert header == ["Name", "HP"]
    assert rows == ["Name: Goblin; HP: 7", "Name: Orc; HP: 15"]


def test_non_pipe_content_returns_empty():
    """Granularity falls back to one atomic embed_unit when this happens."""
    header, rows = linearize_table("Just some prose that got mis-tagged as a table.")
    assert header == []
    assert rows == []


def test_emphasis_stripped_from_header_and_cells():
    text = (
        "| **Name** | **HP** |\n"
        "|---|---|\n"
        "| *Goblin* | 7 |\n"
    )
    header, rows = linearize_table(text)
    assert header == ["Name", "HP"]
    assert rows == ["Name: Goblin; HP: 7"]

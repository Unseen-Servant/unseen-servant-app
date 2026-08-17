"""Stage F (embed units) — ~400-char prose splits + per-row table units
(plan §3.2 F). Pure over Chunks."""
from domain.models import BBox, BBoxSpan, Chunk, ChunkKind
from ingest.linearize import coverage_ratio, linearize_table, to_units, UNIT_CAP


def chunk(text, kind=ChunkKind.prose, page_start=0, page_end=0):
    return Chunk(id="d:c0", doc_id="d", section_id="s", ordinal=0, kind=kind, text=text,
                 page_start=page_start, page_end=page_end,
                 bbox_spans=(BBoxSpan(page=0, bbox=BBox(0, 0, 10, 10)),), lang="en")


def test_short_prose_is_one_unit():
    u = to_units(chunk("A goblin has armor class 15."))
    assert len(u) == 1 and u[0].text == "A goblin has armor class 15." and u[0].kind is ChunkKind.prose


def test_long_prose_splits_at_word_boundary_no_loss():
    units = to_units(chunk(" ".join(["word"] * 300)))  # ~1500 chars
    assert len(units) > 1
    assert all(len(u.text) <= UNIT_CAP for u in units)
    assert " ".join(u.text for u in units).split() == ["word"] * 300  # nothing lost, no mid-word split
    assert all(u.text == u.text.strip() for u in units)


def test_table_is_one_unit_per_row():
    units = to_units(chunk("Club 1d4 Bludgeoning\nDagger 1d6 Piercing\nSpear 1d6 Piercing", kind=ChunkKind.table))
    assert len(units) == 3
    assert units[0].text == "Club 1d4 Bludgeoning" and units[0].kind is ChunkKind.table


def test_table_skips_blank_rows():
    units = to_units(chunk("Row A\n\nRow B", kind=ChunkKind.table))
    assert [u.text for u in units] == ["Row A", "Row B"]


def test_units_carry_chunk_id_pages_lang_and_id():
    u = to_units(chunk("short", page_start=3, page_end=4))[0]
    assert u.chunk_id == "d:c0" and u.id.startswith("d:c0:u")
    assert u.page_start == 3 and u.page_end == 4 and u.lang == "en"


# -- rung 3: pipe-cell tables reformat to "<header>: <cell>; ..." (ported v2 win) --

def test_pipe_table_reformats_header_cell():
    txt = "Weapon | Damage | Cost\nClub | 1d4 | 5 gp\nDagger | 1d6 | 2 gp"
    units = to_units(chunk(txt, kind=ChunkKind.table))
    assert units[0].text == "Weapon: Club; Damage: 1d4; Cost: 5 gp"
    assert units[1].text == "Weapon: Dagger; Damage: 1d6; Cost: 2 gp"
    assert units[0].kind is ChunkKind.table


def test_pipe_table_skips_empty_cells():
    txt = "Name | Damage | Notes\nClub | 1d4 | \nNet |  | entangles"
    units = to_units(chunk(txt, kind=ChunkKind.table))
    assert units[0].text == "Name: Club; Damage: 1d4"          # empty Notes skipped
    assert units[1].text == "Name: Net; Notes: entangles"       # empty Damage skipped


def test_title_row_demoted_when_no_separator():
    # BFRPG-style single-cell title above the real multi-cell header (no md separator in v3)
    txt = "Armor Table\nType | AC | Cost\nLeather | 12 | 20 gp"
    units = to_units(chunk(txt, kind=ChunkKind.table))
    assert units[0].text == "Type: Leather; AC: 12; Cost: 20 gp"


def test_non_pipe_table_falls_back_to_bare_rows():
    units = to_units(chunk("Club 1d4 Bludgeoning\nDagger 1d6 Piercing", kind=ChunkKind.table))
    assert [u.text for u in units] == ["Club 1d4 Bludgeoning", "Dagger 1d6 Piercing"]


def test_lossy_parse_falls_back_to_bare_rows():
    # header far narrower than data → truncation drops most content → coverage guard trips
    txt = "A |\n1 | 2 | 3 | 4 | 5 | 6\n7 | 8 | 9 | 10 | 11 | 12"
    units = to_units(chunk(txt, kind=ChunkKind.table))
    assert units[1].text == "1 | 2 | 3 | 4 | 5 | 6"  # raw row, not reformatted


def test_coverage_ratio_high_for_faithful_low_for_truncated():
    h, s = linearize_table("A | B\n1 | 2\n3 | 4")
    assert coverage_ratio("A | B\n1 | 2\n3 | 4", h, s) >= 0.6
    h2, s2 = linearize_table("A |\n1 | 2 | 3 | 4 | 5 | 6")
    assert coverage_ratio("A |\n1 | 2 | 3 | 4 | 5 | 6", h2, s2) < 0.6

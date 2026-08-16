"""Stage F (embed units) — ~400-char prose splits + per-row table units
(plan §3.2 F). Pure over Chunks."""
from domain.models import BBox, BBoxSpan, Chunk, ChunkKind
from ingest.linearize import to_units, UNIT_CAP


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

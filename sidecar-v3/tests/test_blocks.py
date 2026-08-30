"""Aggregation on synthetic geometry. Points are PDF points, y-down from the
top-left, matching every Span the pipeline carries."""
from domain.models import BBox
from ingest.blocks import bands, build, cells, em, rows
from ingest.raw import Span

EM = 10.0


def _obj(text: str, x: float, y: float = 0.0, width: float | None = None) -> Span:
    """One Span per PDFium text object, laid out left to right on a 10pt em."""
    return Span(text, BBox(x, y, x + (len(text) * 6.0 if width is None else width), y + EM), EM, "")


def test_em_is_the_median_object_height():
    assert em([_obj("abc", 0)]) == EM


def test_a_wide_gap_starts_a_new_cell():
    """A table row's inter-cell gap is wide relative to the type size. The old
    absolute threshold (18pt) merged whole rows into one line."""
    row = [_obj("AB", 0), _obj("CD", 100)]
    assert [tuple(w.text for w in cell) for cell in cells(row, EM)] == [("AB",), ("CD",)]


def test_a_space_sized_gap_starts_a_new_word_not_a_new_cell():
    row = [_obj("AB", 0), _obj("CD", 15)]
    assert [tuple(w.text for w in cell) for cell in cells(row, EM)] == [("AB", "CD")]


def test_abutting_objects_merge_into_one_word():
    """osric_2e p.40 splits words across text objects mid-word — 'Find ' + ' T'
    + 'r' + 'aps '. Adjacent objects with no meaningful gap are one word."""
    row = [_obj("Find", 0), _obj("T", 26), _obj("r", 32), _obj("aps", 38)]
    assert [tuple(w.text for w in cell) for cell in cells(row, EM)] == [("Find", "Traps")]


def test_a_row_spanning_object_is_never_split():
    """Objects are atomic. A wide object is one cell, not several — splitting on
    internal gaps is the failure mode this design exists to remove."""
    row = [_obj("A B", 0, width=200.0)]
    assert [tuple(w.text for w in cell) for cell in cells(row, EM)] == [("A B",)]


def test_rows_group_by_baseline_and_order_top_to_bottom():
    assert [[s.text for s in row]
            for row in rows([_obj("B", 0, y=40.0), _obj("T", 0, y=0.0)], EM)] == [["T"], ["B"]]


PAGE_W, PAGE_H = 400.0, 200.0


def _two_columns() -> list[Span]:
    """Left column at x=20, right at x=240, sharing baselines — the layout that
    produces synthetic cross-column rows when a gutter is not detected."""
    out: list[Span] = []
    for i, y in enumerate((0.0, 20.0, 40.0)):
        out += [_obj(f"L{i}", 20.0, y=y), _obj(f"R{i}", 240.0, y=y)]
    return out


def test_bands_find_the_gutter_between_two_columns():
    found = bands(_two_columns(), PAGE_W, EM)
    assert len(found) == 2
    assert found[0][1] < 240.0 <= found[1][0]


def test_a_single_column_page_is_one_band():
    assert len(bands([_obj("ABC", 20.0)], PAGE_W, EM)) == 1


def test_build_reads_the_left_column_before_the_right():
    text = " ".join(b.text for b in build(_two_columns(), PAGE_W, PAGE_H))
    assert text.index("L2") < text.index("R0"), text


def test_build_conserves_every_run():
    spans = _two_columns()
    produced = "".join(s.text for b in build(spans, PAGE_W, PAGE_H) for s in b.spans)
    assert sorted(produced.replace(" ", "")) == sorted("".join(s.text for s in spans).replace(" ", ""))


def test_no_block_straddles_a_band_boundary():
    found = bands(_two_columns(), PAGE_W, EM)
    boundary = (found[0][1] + found[1][0]) / 2
    for block in build(_two_columns(), PAGE_W, PAGE_H):
        starts_left = block.bbox.x0 < boundary
        assert all((s.bbox.x0 < boundary) == starts_left for s in block.spans)


def _prose(text: str, y: float) -> Span:
    """A full-width prose line: one cell spanning the whole text column."""
    return _obj(text, 20.0, y=y, width=300.0)


def test_consecutive_prose_rows_become_one_block():
    """PyMuPDF groups a paragraph's lines into a single block; one block per
    line is the hierarchy failure that disqualified the pdfplumber adapter."""
    spans = [_prose("first line", 0.0), _prose("second line", 12.0), _prose("third line", 24.0)]
    blocks = build(spans, PAGE_W, PAGE_H)
    assert len(blocks) == 1
    assert [line.text for line in blocks[0].lines] == ["first line", "second line", "third line"]


def test_a_wide_vertical_gap_starts_a_new_block():
    spans = [_prose("end of one", 0.0), _prose("start of another", 60.0)]
    assert len(build(spans, PAGE_W, PAGE_H)) == 2


def test_a_multi_cell_row_stays_one_block_per_cell():
    """Table rows keep cell atomicity — that is what table_cells measures."""
    spans = [_obj("Gambeson", 20.0, y=0.0), _obj("50", 200.0, y=0.0)]
    blocks = build(spans, PAGE_W, PAGE_H)
    assert [b.text for b in blocks] == ["Gambeson", "50"]


def test_a_table_row_interrupts_the_paragraph_above_it():
    spans = [_prose("prose line", 0.0),
             _obj("Gambeson", 20.0, y=12.0), _obj("50", 200.0, y=12.0),
             _prose("more prose", 24.0)]
    assert [b.text for b in build(spans, PAGE_W, PAGE_H)] == [
        "prose line", "Gambeson", "50", "more prose"]


def test_paragraph_grouping_never_merges_across_a_gutter():
    """With band assignment collapsed, left- and right-column prose lines at the
    same y would merge into one paragraph. cells() cannot prevent this — only
    correct band assignment can."""
    spans = []
    for i, y in enumerate((0.0, 12.0, 24.0)):
        spans.append(_obj(f"left{i}", 20.0, y=y, width=120.0))
        spans.append(_obj(f"right{i}", 240.0, y=y, width=120.0))
    blocks = build(spans, PAGE_W, PAGE_H)
    assert len(blocks) == 2, [b.text for b in blocks]
    assert [line.text for line in blocks[0].lines] == ["left0", "left1", "left2"]
    assert [line.text for line in blocks[1].lines] == ["right0", "right1", "right2"]

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

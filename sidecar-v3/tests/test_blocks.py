"""Aggregation on synthetic geometry. Points are PDF points, y-down from the
top-left, matching every Span the pipeline carries."""
from domain.models import BBox
from ingest.blocks import cells, em, rows
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

from domain.models import BBox
from ingest.extract import Span
from ingest.pdfium_extract import _line_spans, _words


def test_words_split_wide_gaps_but_keep_character_runs():
    chars = [
        Span("g", BBox(0, 0, 4, 8), 8, ""), Span("o", BBox(5, 0, 9, 8), 8, ""),
        Span("b", BBox(16, 0, 20, 8), 8, ""), Span("l", BBox(21, 0, 24, 8), 8, ""),
    ]
    assert [word.text for word in _words(chars)] == ["go", "bl"]


def test_line_spans_separates_same_y_columns():
    class TextPage:
        def count_chars(self):
            return 4

        def get_text_range(self, index, count):
            return "ABCD"[index:index + count]

        def get_charbox(self, index):
            return [(10, 10, 14, 18), (15, 10, 19, 18), (100, 10, 104, 18), (105, 10, 109, 18)][index]

    lines = _line_spans(TextPage())
    assert [[span.text for span in line] for line in lines] == [["A", "B"], ["C", "D"]]

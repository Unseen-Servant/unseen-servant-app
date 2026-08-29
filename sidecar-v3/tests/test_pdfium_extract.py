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

    lines = _line_spans(TextPage(), PAGE_HEIGHT)
    assert [[span.text for span in line] for line in lines] == [["A", "B"], ["C", "D"]]


def _text_page(charboxes, text):
    """Minimal PdfTextPage stand-in. Charboxes are PDFium page space:
    (x0, y0, x1, y1) with y measured *up* from the bottom of the page."""
    class TextPage:
        def count_chars(self):
            return len(charboxes)

        def get_text_range(self, index, count):
            return text[index:index + count]

        def get_charbox(self, index):
            return charboxes[index]
    return TextPage()


PAGE_HEIGHT = 100.0


def test_line_spans_orders_the_top_of_the_page_first():
    """PDFium measures y up from the bottom of the page; PyMuPDF and the rest
    of the pipeline measure it down from the top. Sorting PDFium's y ascending
    walks the page bottom-to-top and inverts every page's reading order."""
    bottom, top = (10, 10, 14, 20), (10, 80, 14, 90)
    lines = _line_spans(_text_page([bottom, top], "BT"), PAGE_HEIGHT)
    assert [[span.text for span in line] for line in lines] == [["T"], ["B"]]


def test_line_spans_reports_top_left_origin_boxes():
    """Spans reach consumers that assume PyMuPDF's y-down boxes — the layout
    model's raster among them — so the flip belongs at the source."""
    lines = _line_spans(_text_page([(10, 80, 14, 90)], "T"), PAGE_HEIGHT)
    assert lines[0][0].bbox == BBox(10, 10, 14, 20)

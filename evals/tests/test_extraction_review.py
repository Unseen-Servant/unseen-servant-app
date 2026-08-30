import pytest

from evals.extraction.review import _native_text, parse_pages, render


def test_parse_pages_supports_ranges_and_deduplicates():
    assert parse_pages("3,5-6,3") == [3, 5, 6]


@pytest.mark.parametrize("value", ["0", "5-3", "word"])
def test_parse_pages_rejects_invalid_ranges(value):
    with pytest.raises(ValueError):
        parse_pages(value)


def test_render_escapes_extracted_text_and_embeds_page_image():
    page = {"page": 3, "image": "abc", "extracted": {"v3": "<rule>"}, "native": "native"}
    report = render("Review", [page], ["v3"])
    assert "data:image/png;base64,abc" in report
    assert "&lt;rule&gt;" in report


def test_render_puts_one_column_per_engine():
    """The point of the comparison view: each engine's text sits beside the
    others under its own heading, so a difference is visible rather than
    inferred."""
    page = {"page": 3, "image": "abc",
            "extracted": {"v2": "from v2", "v3 (pdfium)": "from v3"}, "native": "native"}
    report = render("Review", [page], ["v2", "v3 (pdfium)"])
    assert "<h3>v2</h3>" in report
    assert "<h3>v3 (pdfium)</h3>" in report
    assert report.index("from v2") < report.index("from v3")


def test_native_text_converts_structured_pymupdf_blocks():
    class Page:
        def get_text(self, kind):
            assert kind == "blocks"
            return [(0, 0, 1, 1, "First\n", 0, 0), (0, 1, 1, 2, "Second\n", 0, 0)]

    assert _native_text(Page()) == "First\n\nSecond"

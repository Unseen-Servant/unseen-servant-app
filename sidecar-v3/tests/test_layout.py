"""Stage B — layout assembly (plan §3.2 B/C/D). Tests the deterministic
region→Block logic with hand-crafted regions (no ONNX model needed); the
PP-DocLayout-M inference is a thin wrapper tested separately when the model is
present."""
from domain.models import BBox, BlockKind
from ingest.extract import PageExtract, Span, TextBlock, TextLine
from ingest.layout import Region, layout_page


def span(text, x0, y0, x1, y1, size=11.0, bold=False):
    return Span(text=text, bbox=BBox(x0, y0, x1, y1), size=size, font="F", bold=bold, italic=False)


def region(label, x0, y0, x1, y1, read_order=None):
    return Region(label=label, bbox=BBox(x0, y0, x1, y1), score=0.9, read_order=read_order)


def text_block(spans):
    rows = {}
    for item in spans:
        rows.setdefault(item.bbox.y0, []).append(item)
    lines = [TextLine(
        BBox(min(item.bbox.x0 for item in row), min(item.bbox.y0 for item in row),
             max(item.bbox.x1 for item in row), max(item.bbox.y1 for item in row)),
        tuple(sorted(row, key=lambda item: item.bbox.x0)),
    ) for _, row in sorted(rows.items())]
    return TextBlock(
        BBox(min(item.bbox.x0 for item in spans), min(item.bbox.y0 for item in spans),
             max(item.bbox.x1 for item in spans), max(item.bbox.y1 for item in spans)),
        tuple(lines),
    )


def page(spans, width=612.0, height=792.0, blocks=None):
    blocks = tuple(blocks) if blocks is not None else ((text_block(spans),) if spans else ())
    return PageExtract(page=0, width=width, height=height,
                       spans=tuple(item for block in blocks for item in block.spans),
                       needs_ocr=False, label="", blocks=blocks)


def test_labels_map_to_blockkinds():
    title = text_block([span("Title", 72, 80, 200, 100, size=18, bold=True)])
    body = text_block([span("body text", 72, 120, 300, 132)])
    p = page([], blocks=[title, body])
    regions = [region("paragraph_title", 70, 78, 210, 102), region("text", 70, 118, 310, 134)]
    blocks = layout_page(p, regions, "d")
    assert any(b.kind == BlockKind.heading and "Title" in b.text for b in blocks)
    assert any(b.kind == BlockKind.prose and "body text" in b.text for b in blocks)


def test_table_maps_to_table_and_linearizes_row_major_with_cells():
    spans = [span("Club", 72, 100, 110, 112), span("1d4", 200, 100, 230, 112),
             span("Dagger", 72, 120, 120, 132), span("1d6", 200, 120, 230, 132)]
    b = layout_page(page(spans), [region("table", 70, 95, 240, 135)], "d")[0]
    assert b.kind == BlockKind.table
    # rung 3: cells within a row are pipe-delimited (a wide x-gap = column break),
    # rows newline-delimited — so linearize.py can pair headers with cells.
    assert b.text == "Club | 1d4\nDagger | 1d6"


def test_table_cells_split_on_large_x_gap_not_small():
    # "Chain Mail" is one cell (tight inter-word gap); "15" a separate column (wide gap).
    spans = [span("Chain", 72, 100, 100, 112), span("Mail", 102, 100, 130, 112),
             span("15", 300, 100, 320, 112)]
    b = layout_page(page(spans), [region("table", 70, 95, 340, 120)], "d")[0]
    assert b.text == "Chain Mail | 15"


def test_furniture_label_never_discards_native_text():
    b = layout_page(page([span("Chapter 3", 72, 40, 150, 52)]), [region("header", 70, 38, 160, 54)], "d")[0]
    assert b.kind == BlockKind.prose and "Chapter 3" in b.text


def test_titles_map_to_caption():
    b = layout_page(page([span("Table 1: Armor", 72, 90, 200, 102)]),
                    [region("table_title", 70, 88, 210, 104)], "d")[0]
    assert b.kind == BlockKind.caption


def test_image_region_kept_with_empty_text():
    blocks = layout_page(page([]), [region("image", 100, 100, 300, 300)], "d")
    assert len(blocks) == 1 and blocks[0].kind == BlockKind.image and blocks[0].text == ""


def test_image_region_never_discards_native_text():
    blocks = layout_page(page([span("Equipment List", 72, 100, 200, 112)]),
                         [region("image", 70, 95, 300, 150)], "d")
    assert len(blocks) == 1 and blocks[0].kind == BlockKind.prose
    assert blocks[0].text == "Equipment List"


def test_uncovered_native_block_is_kept_as_prose():
    # A detector gap cannot discard or attach native text to another column.
    b = layout_page(page([span("orphan", 72, 200, 150, 212)]), [region("text", 70, 100, 300, 150)], "d")[0]
    assert b.kind == BlockKind.prose and b.text == "orphan" and b.bbox.y0 == 200


def test_detector_gap_does_not_merge_same_y_columns():
    left = text_block([span("Goblin", 72, 100, 140, 112), span("Armor Class 15", 72, 120, 190, 132)])
    right = text_block([span("Hobgoblin", 340, 100, 440, 112), span("Armor Class 18", 340, 120, 470, 132)])
    blocks = layout_page(page([], blocks=[left, right]), [region("text", 70, 95, 210, 140)], "d")
    assert [block.text for block in blocks] == ["Goblin\nArmor Class 15", "Hobgoblin\nArmor Class 18"]


def test_two_column_reading_order_via_xy_cut():
    spans = [span("L1", 72, 100, 200, 112), span("L2", 72, 400, 200, 412),
             span("R1", 340, 100, 500, 112), span("R2", 340, 400, 500, 412)]
    regions = [region("text", 70, 95, 210, 120), region("text", 70, 395, 210, 420),
               region("text", 330, 95, 510, 120), region("text", 330, 395, 510, 420)]  # no read_order
    blocks = layout_page(page([], blocks=[text_block([item]) for item in spans]), regions, "d")
    assert [b.text.strip() for b in blocks] == ["L1", "L2", "R1", "R2"]  # left col top→bottom, then right


def test_full_width_heading_does_not_interleave_following_columns():
    title = text_block([span("Rules", 72, 40, 540, 52, size=18, bold=True)])
    left = [text_block([span(f"L{i}", 72, y, 200, y + 12)]) for i, y in enumerate((100, 200), 1)]
    right = [text_block([span(f"R{i}", 340, y, 500, y + 12)]) for i, y in enumerate((100, 200), 1)]
    blocks = layout_page(page([], blocks=[title, *left, *right]), [], "d")
    assert [block.text for block in blocks] == ["Rules", "L1", "L2", "R1", "R2"]


def test_native_block_order_does_not_follow_detector_order():
    spans = [span("second", 72, 100, 200, 112), span("first", 72, 400, 200, 412)]
    regions = [region("text", 70, 95, 210, 120, read_order=5), region("text", 70, 395, 210, 420, read_order=1)]
    blocks = layout_page(page([], blocks=[text_block([item]) for item in spans]), regions, "d")
    assert [b.text.strip() for b in blocks] == ["second", "first"]


def test_tall_heading_span_does_not_merge_into_stat_row():
    # Regression (black_hack warrior g25): a big-font title ("WARRIOR", size 24,
    # tall bbox centered on the first stat line) must NOT merge into it — that
    # broke the contiguous cell "Starting HP : d10 + 4" and cost the Phase-2 gate.
    spans = [
        span("WARRIOR", 150, 18, 230, 122, size=24.0, bold=True),
        span("Starting HP :", 99, 63, 150, 78),
        span("d10", 160, 63, 180, 78),
        span("+ 4", 176, 63, 200, 78, size=10.0),
    ]
    b = layout_page(page(spans), [region("table", 95, 10, 240, 130)], "d")[0]
    lines = [ln for ln in b.text.split("\n") if ln.strip()]
    stat = next(ln for ln in lines if "Starting HP" in ln)
    assert "d10" in stat and "+ 4" in stat and "WARRIOR" not in stat
    assert any(ln.strip() == "WARRIOR" for ln in lines)


def test_blocks_carry_page_bbox_readingorder_id_and_fontstats():
    b = layout_page(page([span("Title", 72, 80, 200, 100, size=18, bold=True)]),
                    [region("paragraph_title", 70, 78, 210, 102)], "d")[0]
    assert b.page == 0 and b.reading_order == 0
    assert b.bbox.x0 == 72
    assert b.font_stats is not None and b.font_stats.size == 18.0 and b.font_stats.bold
    assert b.id.startswith("d:p0:")

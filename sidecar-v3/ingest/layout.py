"""B/C/D. Layout → typed blocks (plan §3.2 B/C/D).

The Stage-1 winner (PP-DocLayout-M ONNX, GO) detects page regions; we use those
regions only to classify native Stage-A text blocks. Classification may split a
raw block only at an existing line boundary; native lines carry their own text
and order, then a column-aware XY-cut orders the resulting blocks. This
prevents an incomplete detector from merging same-y spans across two columns.

Split for testability: `layout_page()` is pure region→Block assembly (unit-
tested with hand-crafted regions); `detect_regions()`/`layout()` are the thin
ONNX inference layer (integration, needs the model asset). No import from sidecar/.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from domain.models import BBox, Block, BlockKind, FontStats
from ingest.extract import PageExtract, RawExtraction, Span, TextBlock, rasterize

# PP-DocLayout label → BlockKind. Covers PP-DocLayout-M's 23 classes (the GO
# model) plus V3's extras, so either model feeds the same assembly.
LABEL_TO_KIND: dict[str, BlockKind] = {
    "doc_title": BlockKind.heading, "paragraph_title": BlockKind.heading,
    "table_title": BlockKind.caption, "figure_title": BlockKind.caption, "chart_title": BlockKind.caption,
    "table": BlockKind.table,
    "image": BlockKind.image, "chart": BlockKind.image,
    "header": BlockKind.artifact, "footer": BlockKind.artifact, "number": BlockKind.artifact,
    "seal": BlockKind.artifact, "header_image": BlockKind.artifact, "footer_image": BlockKind.artifact,
    "text": BlockKind.prose, "abstract": BlockKind.prose, "content": BlockKind.prose,
    "reference": BlockKind.prose, "reference_content": BlockKind.prose, "footnote": BlockKind.prose,
    "algorithm": BlockKind.prose, "aside_text": BlockKind.prose, "formula": BlockKind.prose,
    "formula_number": BlockKind.prose, "display_formula": BlockKind.prose, "inline_formula": BlockKind.prose,
    "vertical_text": BlockKind.prose, "vision_footnote": BlockKind.prose,
}
# PP-DocLayout-M label list (index = label_index), from the layout spike.
LABELS_M = [
    "paragraph_title", "image", "text", "number", "abstract", "content", "figure_title", "formula",
    "table", "table_title", "reference", "doc_title", "footnote", "header", "algorithm", "footer",
    "seal", "chart_title", "chart", "formula_number", "header_image", "footer_image", "aside_text",
]


@dataclass(frozen=True, slots=True)
class Region:
    """A detected layout region, bbox in PDF points. `read_order` is the model's
    own reading-order field (PP-DocLayoutV3) or None (PicoDet M/S → XY-cut)."""

    label: str
    bbox: BBox
    score: float = 1.0
    read_order: float | None = None


def _kind(label: str) -> BlockKind:
    return LABEL_TO_KIND.get(label, BlockKind.prose)


# ---- pure assembly (unit-tested, no model) ----

def _xy_cut(items: Sequence, page_w: float) -> list:
    if len(items) <= 1:
        return list(items)
    mid = page_w / 2.0
    cx = lambda item: (item.bbox.x0 + item.bbox.x1) / 2.0
    full = [item for item in items
            if item.bbox.x0 < mid and item.bbox.x1 > mid
            and (item.bbox.x1 - item.bbox.x0) > page_w * 0.55]
    columns = [item for item in items if item not in full]
    left = [item for item in columns if cx(item) < mid]
    right = [item for item in columns if cx(item) >= mid]
    if left and right:
        def ordered_columns(group):
            group_left = [item for item in group if cx(item) < mid]
            group_right = [item for item in group if cx(item) >= mid]
            return sorted(group_left, key=lambda item: item.bbox.y0) + sorted(group_right, key=lambda item: item.bbox.y0)

        # Full-width titles and tables partition a two-column page; they must
        # not force the surrounding columns back into y-major interleaving.
        out = []
        remaining = columns
        for item in sorted(full, key=lambda item: item.bbox.y0):
            before = [candidate for candidate in remaining if candidate.bbox.y0 < item.bbox.y0]
            out.extend(ordered_columns(before))
            out.append(item)
            remaining = [candidate for candidate in remaining if candidate not in before]
        out.extend(ordered_columns(remaining))
        return out
    return sorted(items, key=lambda item: item.bbox.y0)


def _cells(row: list[Span]) -> list[str]:
    """Group a row's spans into cells: a horizontal gap wider than a column break
    (≈1.3 font heights) starts a new cell; tight inter-word gaps stay in one."""
    row = sorted(row, key=lambda s: s.bbox.x0)
    cells: list[list[Span]] = [[row[0]]]
    for prev, s in zip(row, row[1:]):
        if s.bbox.x0 - prev.bbox.x1 > max(8.0, 1.3 * max(prev.size, s.size)):
            cells.append([s])
        else:
            cells[-1].append(s)
    return [" ".join(x.text for x in c) for c in cells]


def _linearize_table(block: TextBlock) -> str:
    """Row-major with pipe-delimited cells, so Stage F can pair headers to cells."""
    return "\n".join(" | ".join(_cells(list(line.spans))) for line in block.lines)


def _font_stats(spans: list[Span]) -> FontStats | None:
    if not spans:
        return None
    n = len(spans)
    return FontStats(
        size=max(s.size for s in spans),
        bold=sum(s.bold for s in spans) * 2 >= n,
        italic=sum(s.italic for s in spans) * 2 >= n,
        name=Counter(s.font for s in spans).most_common(1)[0][0],
    )


def _overlap_fraction(block: BBox, region: BBox) -> float:
    width = max(0.0, min(block.x1, region.x1) - max(block.x0, region.x0))
    height = max(0.0, min(block.y1, region.y1) - max(block.y0, region.y0))
    area = max(0.0, block.x1 - block.x0) * max(0.0, block.y1 - block.y0)
    return width * height / area if area else 0.0


def _bbox(lines) -> BBox:
    return BBox(
        min(line.bbox.x0 for line in lines), min(line.bbox.y0 for line in lines),
        max(line.bbox.x1 for line in lines), max(line.bbox.y1 for line in lines),
    )


def _classified_blocks(native: TextBlock, regions: Sequence[Region]) -> tuple[list[tuple[TextBlock, BlockKind]], set[int]]:
    """Split only at native line boundaries when layout classification changes."""
    out: list[tuple[TextBlock, BlockKind]] = []
    covered_regions: set[int] = set()
    lines = []
    kind = None
    for line in native.lines:
        scored = [(_overlap_fraction(line.bbox, region.bbox), i) for i, region in enumerate(regions)]
        fraction, region_i = max(scored, default=(0.0, -1))
        line_kind = _kind(regions[region_i].label) if fraction > 0.5 else BlockKind.prose
        # Detection labels are advisory, not permission to discard native text.
        # The current model mislabels real tables and rule headings as images or
        # furniture, so retain every text-bearing line until a separately
        # validated furniture pass can prove it is safe to remove.
        if line_kind in {BlockKind.image, BlockKind.artifact}:
            line_kind = BlockKind.prose
        if region_i >= 0 and fraction > 0.5:
            covered_regions.add(region_i)
        if lines and line_kind is not kind:
            out.append((TextBlock(_bbox(lines), tuple(lines)), kind))
            lines = []
        lines.append(line)
        kind = line_kind
    if lines:
        out.append((TextBlock(_bbox(lines), tuple(lines)), kind))
    return out, covered_regions


def layout_page(page: PageExtract, regions: Sequence[Region], doc_id: str) -> tuple[Block, ...]:
    """Classify and order native text blocks without rewriting their content."""
    blocks: list[Block] = []
    covered_regions: set[int] = set()
    classified: dict[int, list[tuple[TextBlock, BlockKind]]] = {}
    for native in page.blocks:
        parts, covered = _classified_blocks(native, regions)
        classified[id(native)] = parts
        covered_regions.update(covered)
    for source_block in _xy_cut(page.blocks, page.width):
        # Split parts inherit their raw block's page position but retain native
        # line sequence. Re-sorting them by their aggregate bboxes can invert a
        # heading and its following prose when PDFs report overlapping line boxes.
        for native, kind in classified[id(source_block)]:
            order = len(blocks)
            text = _linearize_table(native) if kind is BlockKind.table else native.text
            blocks.append(Block(
                id=f"{doc_id}:p{page.page}:b{order}",
                kind=kind,
                text=text,
                page=page.page,
                bbox=native.bbox,
                reading_order=order,
                font_stats=_font_stats(list(native.spans)),
                lang=None,
            ))
    for i, region in enumerate(regions):
        if _kind(region.label) is BlockKind.image and i not in covered_regions:
            order = len(blocks)
            blocks.append(Block(
                id=f"{doc_id}:p{page.page}:b{order}", kind=BlockKind.image, text="",
                page=page.page, bbox=region.bbox, reading_order=order, font_stats=None, lang=None,
            ))
    return tuple(blocks)


# ---- ONNX inference layer (integration; needs the PP-DocLayout model asset) ----

def detect_regions(raster, session, labels: list[str] = LABELS_M, conf: float = 0.5) -> list[Region]:
    """Run a PP-DocLayout ONNX model on an RGB raster → regions in RASTER PIXELS.

    Introspects input size (800 V3 / 640 M) + input names. `layout()` converts
    the pixel boxes to PDF points via the raster DPI.
    """
    import numpy as np
    from PIL import Image

    names = [i.name for i in session.get_inputs()]
    size = session.get_inputs()[names.index("image")].shape[-1]
    H, W = raster.shape[:2]
    im = np.asarray(Image.fromarray(raster).resize((size, size), Image.BILINEAR), np.float32) / 255.0
    im = (im - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    feed = {"image": im.transpose(2, 0, 1)[None].astype(np.float32)}
    if "scale_factor" in names:
        feed["scale_factor"] = np.array([[size / H, size / W]], np.float32)
    if "im_shape" in names:
        feed["im_shape"] = np.array([[size, size]], np.float32)
    out = session.run(None, feed)[0]
    dets = out[:, 1:] if out.shape[1] == 8 else out  # drop img_idx if batched export
    has_ro = dets.shape[1] >= 7
    regions = []
    for d in dets:
        if d[1] <= conf:
            continue
        regions.append(Region(
            label=labels[int(d[0])],
            bbox=BBox(float(d[2]), float(d[3]), float(d[4]), float(d[5])),
            score=float(d[1]),
            read_order=float(d[6]) if has_ro else None,
        ))
    return regions


def _px_to_pt(regions: list[Region], dpi: int) -> list[Region]:
    s = 72.0 / dpi
    return [Region(r.label, BBox(r.bbox.x0 * s, r.bbox.y0 * s, r.bbox.x1 * s, r.bbox.y1 * s),
                   r.score, r.read_order) for r in regions]


def layout(raw: RawExtraction, session, labels: list[str] = LABELS_M, dpi: int = 150,
           rasterizer=rasterize) -> tuple[Block, ...]:
    """Full Stage B over a document: rasterize each page → detect → assemble,
    with a document-global reading_order."""
    blocks: list[Block] = []
    for pe in raw.pages:
        raster = rasterizer(raw.path, pe.page, dpi=dpi)
        regions = _px_to_pt(detect_regions(raster, session, labels), dpi)
        for b in layout_page(pe, regions, raw.doc_id):
            blocks.append(Block(b.id, b.kind, b.text, b.page, b.bbox,
                                len(blocks), b.font_stats, b.lang))
    return tuple(blocks)

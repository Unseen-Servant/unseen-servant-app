"""B/C/D. Layout → typed blocks (plan §3.2 B/C/D).

The Stage-1 winner (PP-DocLayout-M ONNX, GO) detects page regions; we map each
to a typed BlockKind, assign the Stage-A text spans, order them column-aware
(the model's read_order if present, else a 2-column XY-cut — the R1 fix), drop
furniture as `artifact` blocks (the R2/R4 fix, by classification not regex), and
linearize each region row-major so table cells stay contiguous.

Split for testability: `layout_page()` is pure region→Block assembly (unit-
tested with hand-crafted regions); `detect_regions()`/`layout()` are the thin
ONNX inference layer (integration, needs the model asset). No import from sidecar/.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from domain.models import BBox, Block, BlockKind, FontStats
from ingest.extract import PageExtract, RawExtraction, Span, rasterize

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

def _center_in(b: BBox, box: BBox) -> bool:
    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
    return box.x0 <= cx <= box.x1 and box.y0 <= cy <= box.y1


def _vdist(b: BBox, box: BBox) -> float:
    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
    dx = max(box.x0 - cx, 0.0, cx - box.x1)
    dy = max(box.y0 - cy, 0.0, cy - box.y1)
    return dy * 3.0 + dx


def _xy_cut(regions: Sequence[Region], page_w: float) -> list[Region]:
    if len(regions) <= 1:
        return list(regions)
    mid = page_w / 2.0
    cx = lambda r: (r.bbox.x0 + r.bbox.x1) / 2.0
    left = [r for r in regions if cx(r) < mid]
    right = [r for r in regions if cx(r) >= mid]
    full = [r for r in regions
            if r.bbox.x0 < mid and r.bbox.x1 > mid and (r.bbox.x1 - r.bbox.x0) > page_w * 0.55]
    if len(left) >= 2 and len(right) >= 2 and len(full) <= 1:
        return sorted(left, key=lambda r: r.bbox.y0) + sorted(right, key=lambda r: r.bbox.y0)
    return sorted(regions, key=lambda r: r.bbox.y0)


def _order(regions: Sequence[Region], page_w: float) -> list[Region]:
    if regions and all(r.read_order is not None for r in regions):
        return sorted(regions, key=lambda r: r.read_order)
    return _xy_cut(regions, page_w)


def _linearize(spans: list[Span]) -> str:
    """Row-major: bucket spans into rows by y, order each row left→right."""
    if not spans:
        return ""
    spans = sorted(spans, key=lambda s: (s.bbox.y0, s.bbox.x0))
    rows, cur, cy = [], [], None
    for s in spans:
        yc = (s.bbox.y0 + s.bbox.y1) / 2
        h = s.bbox.y1 - s.bbox.y0
        if cy is None or abs(yc - cy) <= max(3.0, h * 0.6):
            cur.append(s); cy = yc if cy is None else (cy + yc) / 2
        else:
            rows.append(cur); cur, cy = [s], yc
    if cur:
        rows.append(cur)
    return "\n".join(" ".join(s.text for s in sorted(row, key=lambda s: s.bbox.x0)) for row in rows)


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


def layout_page(page: PageExtract, regions: Sequence[Region], doc_id: str) -> tuple[Block, ...]:
    """Assemble typed Blocks for one page from detected regions + Stage-A spans."""
    ordered = _order(regions, page.width)
    nonfurn = [i for i, r in enumerate(ordered) if _kind(r.label) is not BlockKind.artifact]
    buckets: list[list[Span]] = [[] for _ in ordered]
    for sp in page.spans:
        host = next((i for i, r in enumerate(ordered) if _center_in(sp.bbox, r.bbox)), None)
        if host is None and nonfurn:  # uncovered content → nearest non-furniture region
            host = min(nonfurn, key=lambda i: _vdist(sp.bbox, ordered[i].bbox))
        if host is not None:
            buckets[host].append(sp)

    blocks: list[Block] = []
    for i, r in enumerate(ordered):
        kind = _kind(r.label)
        sps = buckets[i]
        if not sps and kind is not BlockKind.image:
            continue  # empty non-image region — nothing to keep
        order = len(blocks)
        blocks.append(Block(
            id=f"{doc_id}:p{page.page}:b{order}",
            kind=kind,
            text="" if kind is BlockKind.image else _linearize(sps),
            page=page.page,
            bbox=r.bbox,
            reading_order=order,
            font_stats=_font_stats(sps),
            lang=None,
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


def layout(raw: RawExtraction, session, labels: list[str] = LABELS_M, dpi: int = 150) -> tuple[Block, ...]:
    """Full Stage B over a document: rasterize each page → detect → assemble,
    with a document-global reading_order."""
    blocks: list[Block] = []
    for pe in raw.pages:
        raster = rasterize(raw.path, pe.page, dpi=dpi)
        regions = _px_to_pt(detect_regions(raster, session, labels), dpi)
        for b in layout_page(pe, regions, raw.doc_id):
            blocks.append(Block(b.id, b.kind, b.text, b.page, b.bbox,
                                len(blocks), b.font_stats, b.lang))
    return tuple(blocks)

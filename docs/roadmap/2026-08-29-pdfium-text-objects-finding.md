# PDFium Text Objects — Do They Bound Table Cells?

**Date:** 2026-08-29
**Status:** finding — measurement complete, feeds Task 4 of [2026-08-29-pdfium-block-builder-plan.md](2026-08-29-pdfium-block-builder-plan.md).
**Question:** PDFium's current adapter reconstructs table cells by splitting a row
of characters wherever a horizontal gap looks wide enough, and that heuristic is
responsible for 13 of 18 quality regressions vs. PyMuPDF (whole rows collapse
into one line). PDF content streams already group glyphs into text-showing
operators — does PDFium expose those groupings as page **text objects**
(`FPDF_PAGEOBJ_TEXT`), and if so, do those objects already bound table cells?

---

## Verdict

## USE TEXT OBJECTS

Across all four probe pages, a PDFium text object **never contains glyphs from
two different table columns**. Where a page's content stream emits one
text-showing operator per cell (3 of 4 pages, near-perfectly), objects and
cells are in 1:1 correspondence. Where a page's content stream emits several
operators per word (1 of 4 pages — unusual per-glyph kerning in `osric_2e`),
objects are *finer* than cells, not coarser: several objects fall inside one
cell, but none straddle a cell boundary. Task 4 should build cells by grouping
text objects by row (y-proximity) and merging same-row objects at small
x-gaps, using `get_bounds()` for placement — never by inferring boundaries
from raw glyph/character gap distribution with no object membership signal,
which is what produces the row-collapse regression today.

---

## Corrected probe code

The brief's sketch (`obj.get_pos()`, iterating `page.get_objects()` with no
form-XObject caveat) does not match the installed API. Fixes applied, verified
against pypdfium2 **5.13.0**:

- `PdfObject` has no `get_pos()`. Use `get_bounds()` → `(left, bottom, right, top)` in PDF page coordinates.
- `obj.type` **does** work — it is a plain instance attribute (`vars(obj)` shows `'type': 1`), not a class-level property, so `dir(PdfObject)` doesn't show it but `obj.type` resolves fine at runtime.
- `page.get_objects()` already recurses into form XObjects by default (`max_depth=15`) — no extra walk needed; none of the four pages had text living only inside a form XObject.
- `FPDFTextObj_GetText(text_object, text_page, buffer, length)` works as documented, returns UTF-16LE, first call with `length=0` to size the buffer.

```python
import json, sys, ctypes

sys.path.insert(0, "sidecar-v3")
import pypdfium2
import pypdfium2.raw as raw

import pymupdf
from ingest.extract import _page_text_blocks

m = json.load(open("evals/corpus.manifest.json"))
CASES = [("osric_2e", 39), ("black_hack_1e", 3), ("yze_srd", 19), ("srd_5_2_1", 33)]

for doc_id, idx in CASES:
    d = next(x for x in m["documents"] if x["id"] == doc_id)
    pdf_path = "evals/corpus/" + d["pdf"]["path"]

    # --- PDFium text objects ---
    pdf = pypdfium2.PdfDocument(pdf_path)
    page = pdf[idx]
    tp = page.get_textpage()
    texts = []
    for obj in page.get_objects():
        if obj.type != raw.FPDF_PAGEOBJ_TEXT:
            continue
        n = raw.FPDFTextObj_GetText(obj.raw, tp.raw, None, 0)
        if n <= 0:
            continue
        buf = ctypes.create_string_buffer(n)
        raw.FPDFTextObj_GetText(
            obj.raw, tp.raw, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), n
        )
        txt = buf.raw.decode("utf-16-le").rstrip("\x00")
        bounds = obj.get_bounds()  # (left, bottom, right, top)
        texts.append((bounds, txt))
    pdf.close()

    print(f"\n=== {doc_id} p{idx + 1}: {len(texts)} PDFium text objects")
    for bounds, txt in texts:
        if txt.strip():
            print(f"   x0={bounds[0]:7.1f} top={bounds[3]:7.1f} {txt[:70]!r}")

    # --- PyMuPDF line reference (cell-per-line ground truth) ---
    with pymupdf.open(pdf_path) as doc:
        lines = [ln.text for b in _page_text_blocks(doc.load_page(idx)) for ln in b.lines]
    print(f"--- PyMuPDF reference: {len(lines)} lines")
    for ln in lines:
        print(f"   {ln[:90]!r}")
```

Run with `uv run --frozen --project sidecar-v3 python3 <script>` from the
worktree root. The kept copy lives at
`/private/tmp/claude-501/-Users-jay-code-unseen-legend-lore/e8d5df65-2407-48b7-b4c1-016b1cb91c2e/scratchpad/probe_text_objects.py`
(scratch only, not committed).

---

## Measurements

| doc | page (1-based) | PDFium text objects (non-empty) | PyMuPDF lines (cell reference) | ratio | cross-column merge observed |
|---|---|---|---|---|---|
| osric_2e | 40 | 608 | 423 | 1.44 | **none** |
| black_hack_1e | 4 | 114 | 114 | 1.00 | **none** |
| yze_srd | 20 | 171 | 155 | 1.10 | **none** |
| srd_5_2_1 | 34 | 250 | 250 | 1.00 | **none** |

"Cross-column merge" was checked by (a) manual inspection of every object in
every table row on all four pages, and (b) a grep across the raw output for
any object whose text contained two cell-shaped tokens (e.g. two `%` values,
which would indicate two adjacent percentage cells glued into one object) —
none found. The only multi-`%` object on any page was ordinary prose
(`'below 1% or increase it above 99%. In other words...'` on osric_2e, a
footnote sentence, not a table cell).

### black_hack_1e p4 — perfect 1:1 (114 objects == 114 cells == 114 PyMuPDF lines)

Equipment table, one object per cell, content matches PyMuPDF's line output
token-for-token:

```
x0= 40.7 top=544.8 'ITEM '        x0=153.3 top=544.9 'COST '   x0=199.1 top=550.9 'USAGE'
x0= 40.4 top=519.2 'Gambeson '    x0=163.1 top=517.5 '50 '     x0=287.1 top=519.0 '2 Armor Points'
x0= 40.6 top=502.1 'Leather '     x0=161.2 top=500.0 '100 '    x0=287.0 top=501.8 '4 Armor Points'
```
PyMuPDF: `'ITEM'`, `'COST'`, `'USAGE'`, `'Gambeson'`, `'50'`, `'2 Armor Points'`, `'Leather'`, `'100'`, `'4 Armor Points'`, ...

### srd_5_2_1 p34 — perfect 1:1 (250 objects == 250 cells == 250 PyMuPDF lines)

Dense 3-column x 3-block spell table:

```
x0= 67.0 top=722.0 'Invisibility '   x0=189.7 top=722.0 'Illusion'   x0=267.5 top=722.1 'C'
x0= 66.9 top=706.8 'Knock '          x0=189.2 top=706.9 'Transmutation'  x0=265.5 top=703.1 '—'
```
PyMuPDF: `'Invisibility'`, `'Illusion'`, `'C'`, `'Knock'`, `'Transmutation'`, `'—'`, ... — exact match, count for count.

### yze_srd p20 — near-1:1 (171 objects vs 155 lines; gap is prose, not table cells)

Weapons table, one object per cell:

```
x0= 59.9 top=698.4 'Unarmed '   x0=141.1 top=694.6 '— '  x0=226.1 top=694.6 '— '  x0=311.3 top=697.7 '1 '  x0=395.6 top=698.4 'Engaged '  x0=481.3 top=694.6 '—'
```
PyMuPDF: `'Unarmed'`, `'—'`, `'—'`, `'1'`, `'Engaged'`, `'—'` — exact match. The
171-vs-155 gap comes entirely from running prose paragraphs below the tables,
where a hyperlinked page reference (`'page 21'`) or a bold lead-in
(`'PUSHING: '`) is its own object but PyMuPDF's line-merger folds it into the
surrounding line — not a table-cell effect.

### osric_2e p40 — the outlier: objects finer than cells, never coarser

This page is the worked example from the brief (`Level Climb Walls Find
Traps Hear Noise Shadows Move Quietly...` collapsing into one line under the
current gap heuristic). Its content stream has unusual per-glyph kerning:
words are frequently split into multiple text-showing operators mid-word
(`'Find '` + `' T'` + `'r'` + `'aps '` for "Find Traps"; `'Chara'` + `'c'` +
`'t'` + `'er'` for "Character"). PyMuPDF's own line output shows the *same*
artifact baked into single lines (`'Find T raps'`, `'Hear N oise'` — note the
spurious internal space), confirming this is a property of the PDF's content
stream, not a PDFium extraction defect.

Critically, **every one of those sub-word objects stays inside the x-range of
its own column** — none straddle two columns:

```
x0=147.9 'Find '   x0=163.8 ' T'   x0=170.5 'r'   x0=173.4 'aps '      <- all inside the "Find Traps" column (148–205)
x0=205.4 'H'       x0=211.7 'e'    x0=216.1 'ar '  x0=223.2 ' N' ...   <- all inside the "Hear Noise" column (205–268)
```

And the numeric data rows underneath — the actual bulk of the table (24 rows
× 9 columns) — are perfect 1:1, same as the other three pages:

```
x0= 55.1 top=683.0 '1 '   x0= 99.7 '80% '  x0=159.0 '25% '  x0=218.4 '10% '  x0=277.5 '20% '  x0=336.8 '20% '  x0=396.1 '30% '  x0=455.5 '35% '  x0=516.9 '1%'
```
matches PyMuPDF's `'1'`, `'80%'`, `'25%'`, `'10%'`, `'20%'`, `'20%'`, `'30%'`, `'35%'`, `'1%'` cell for cell.

So on the one page where alignment isn't clean 1:1, the failure mode is
**over-segmentation within a cell** (several objects per cell), which a
same-row, small-x-gap merge step recovers cheaply — never
**under-segmentation across cells** (one object spanning two columns), which
is what the current gap-based heuristic actually produces and cannot be fixed
by adjusting a single global threshold without also risking a merge across a
real column boundary elsewhere on the same page.

---

## Why this decides it

The current adapter's failure (whole row → one line) requires an object, or a
run of glyphs treated as if it were one, to span multiple columns. That never
happened for any text object on any of the four probed pages, including the
one whose row-collapse bug motivated this spike. Text-object membership is
therefore a safe upper bound on cell width: grouping by object never produces
a cell wider than the true cell, only (occasionally, on kerning-heavy PDFs)
narrower — an easy problem (merge adjacent same-row objects at small gaps) vs.
the current hard problem (split a already-merged run of glyphs from raw
gap distribution with no boundary signal at all).

## What Task 4 still has to handle

- Row grouping across `top` values needs a y-tolerance: some header cells
  wrap to two lines within the same logical cell at slightly different `top`
  (e.g. `"Hide in"` / `"Shadows"` on osric_2e, two lines ~9.6pt apart that are
  one cell), and `"Read"` / `"Languages"` likewise. A pure single-`top` bucket
  will split those into two rows.
- On kerning-heavy PDFs (osric_2e headers/prose), several text objects need
  merging into one cell via a small-x-gap-within-row rule — the "gaps" step
  isn't eliminated, it just moves from character-level (unsafe, causes the
  regression) to object-level (safe, bounded by the 1:1 evidence above).

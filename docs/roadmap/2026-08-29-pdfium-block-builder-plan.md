# PDFium Block Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the AGPL PyMuPDF extraction backend with PDFium plus a
purpose-built block builder that reaches the W1 quality reference on the 40-page
golden suite.

**Architecture:** PDFium supplies character geometry. A new backend-neutral
module `ingest/blocks.py` owns all aggregation — characters into words, words
into cells, cells into lines, lines into column-bounded blocks — because PDF has
no block primitive and MuPDF's blocks are themselves a synthesized heuristic.
The raw typed dataclasses move out of the PyMuPDF module into `ingest/raw.py` so
no aggregation or candidate backend transitively imports PyMuPDF.

**Tech Stack:** Python 3.12, uv (`--frozen`), pypdfium2 5.13.0 (BSD-3-Clause /
Apache-2.0), pytest, ONNX Runtime for the layout model.

**Spec:** `docs/roadmap/2026-08-28-permissive-pdf-backend-plan.md`

## Global Constraints

- Every shipped component must carry a `third_party/POLICY.md` allowlisted
  license: Apache-2.0, MIT, ISC, BSD-2-Clause, BSD-3-Clause, Zlib, HPND, or a
  public-domain dedication.
- No PyTorch anywhere in packaged code — ONNX only (sidecar-v3 constitution #1).
- `sidecar-v3/` must not import from `sidecar/`, and vice versa (constitution #7).
- Typed models in `domain/models.py` carry the IR; markdown is never the IR
  (constitution #6).
- Gate reference: `evals/baselines/2026-08-29-v3-w1-reference.json` —
  content_recall 1.000, reading_order 1.000, table_cells 0.982, 0 per-page
  regressions. **Any** per-page metric below reference is a NO-GO.
- **Anti-overfitting rule.** Tunable constants live in one `TUNING` dict at the
  top of `blocks.py` and may be tuned only against the ten section 4.3 fixture
  pages: g06, g08, g09, g10, g28, g33, g34, g35, g39, g40. The 40-page golden
  set is the gate — run after tuning, never during. A failing golden page earns
  a structural change or becomes a new fixture by deliberate commit, never a
  constant nudged until it goes green.
- Two invariants hold on every page: **conservation** (every input character
  appears in exactly one output block) and **no-straddle** (no block's spans
  cross a column-band boundary).
- Indexing a representative 400-page book must stay under 15 minutes.
- Full test command: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests`
- Commit directly to `main`, signed. End messages with the standard
  `Co-Authored-By` trailer.

---

## File Structure

| file | responsibility |
|---|---|
| `sidecar-v3/ingest/raw.py` | **create** — backend-neutral typed raw-extraction dataclasses (`Span`, `TextLine`, `TextBlock`, `PageExtract`, `RawExtraction`) and `_norm_ws`. Imports no PDF library. |
| `sidecar-v3/ingest/extract.py` | **modify** — keeps only the PyMuPDF Stage-A implementation; imports its types from `raw.py`. |
| `sidecar-v3/ingest/blocks.py` | **create** — all aggregation. `build(spans, width, height) -> tuple[TextBlock, ...]`, one Span per atomic text run. Imports no PDF library. |
| `sidecar-v3/ingest/pdfium_extract.py` | **modify** — thin: PDFium characters → `Span`s → `blocks.build()` → `RawExtraction`, plus document metadata. |
| `sidecar-v3/ingest/pdfium_meta.py` | **create** — title, TOC, and printed page labels from PDFium. |
| `sidecar-v3/tests/test_blocks.py` | **create** — merging, banding, and block grouping on synthetic geometry. |
| `sidecar-v3/tests/test_raw_is_backend_neutral.py` | **create** — asserts `ingest.raw` and `ingest.blocks` import no PDF library. |
| `sidecar-v3/tests/test_pdfium_extract.py` | **modify** — rewired to the new seam. |
| `sidecar-v3/tests/test_pdfium_meta.py` | **create** — metadata parity. |
| `third_party/components.json` | **modify** — inventory records. |

---

### Task 1: Close the third-party inventory gap

`pdfplumber` and its `pdfminer.six` dependency are declared in
`sidecar-v3/pyproject.toml` but absent from the inventory, which spec section
4.1 requires before a package becomes a runtime dependency. The check script
validates records that exist; it cannot see a dependency never declared.

**Files:**
- Modify: `third_party/components.json`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks. Independent.

- [ ] **Step 1: Confirm the exact installed versions**

Run: `uv run --frozen --project sidecar-v3 python -c "import importlib.metadata as md; print(md.version('pdfplumber'), md.version('pdfminer.six'))"`
Expected: `0.11.10 20260107`

- [ ] **Step 2: Add both records**

Insert into the `components` array of `third_party/components.json`, after the
`pypdfium2` entry:

```json
    {
      "name": "pdfplumber",
      "version": "0.11.10",
      "kind": "python-runtime",
      "license": "MIT",
      "upstream": "https://github.com/jsvine/pdfplumber",
      "distribution": "v3 evaluation reference",
      "status": "review_required",
      "replacement": "Retained as the table-cell segmentation reference during the backend replacement; drop it or approve it with notices before v3 packaging."
    },
    {
      "name": "pdfminer.six",
      "version": "20260107",
      "kind": "python-runtime",
      "license": "MIT",
      "upstream": "https://github.com/pdfminer/pdfminer.six",
      "distribution": "v3 evaluation reference (pdfplumber dependency)",
      "status": "review_required",
      "replacement": "Transitive dependency of pdfplumber; drop with it or approve with notices before v3 packaging."
    },
```

- [ ] **Step 3: Validate the inventory**

Run: `uv run --frozen --project sidecar-v3 python scripts/check-third-party.py`
Expected: `third-party inventory valid: 11 components, 8 pending release review`

- [ ] **Step 4: Commit**

```bash
git add third_party/components.json
git commit -m "chore(licensing): declare pdfplumber and pdfminer.six in the inventory"
```

---

### Task 2: Extract backend-neutral raw types into `ingest/raw.py`

`layout.py`, `pipeline.py`, `pdfium_extract.py`, and `pdfplumber_extract.py` all
import their types from `ingest.extract`, which imports `pymupdf`. Every
candidate backend therefore transitively depends on the library being replaced,
and PyMuPDF cannot be removed at P4 while that holds.

**Files:**
- Create: `sidecar-v3/ingest/raw.py`
- Modify: `sidecar-v3/ingest/extract.py`
- Modify: `sidecar-v3/ingest/pdfium_extract.py:17`, `sidecar-v3/ingest/pdfplumber_extract.py:9`, `sidecar-v3/ingest/layout.py:20`, `sidecar-v3/ingest/pipeline.py:24`
- Test: `sidecar-v3/tests/test_raw_is_backend_neutral.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ingest.raw` exporting `Span`, `TextLine`, `TextBlock`,
  `PageExtract`, `RawExtraction`, `norm_ws(text: str) -> str`. Every later task
  imports its types from here.

- [ ] **Step 1: Write the failing test**

Create `sidecar-v3/tests/test_raw_is_backend_neutral.py`:

```python
"""The raw types and the aggregation must not depend on any PDF library —
PyMuPDF is being removed, and a candidate backend that transitively imports it
cannot be evaluated honestly or shipped."""
import subprocess
import sys

PDF_LIBS = ("pymupdf", "fitz", "pdfplumber", "pdfminer", "pypdfium2")


def _imported_modules(module: str) -> set[str]:
    code = f"import {module}, sys; print(' '.join(sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True).stdout
    return set(out.split())


def test_raw_imports_no_pdf_library():
    assert not PDF_LIBS_IN(_imported_modules("ingest.raw"))


def PDF_LIBS_IN(modules: set[str]) -> set[str]:
    return {name for name in modules if name.split(".")[0] in PDF_LIBS}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_raw_is_backend_neutral.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.raw'`

- [ ] **Step 3: Create `ingest/raw.py`**

Move verbatim from `ingest/extract.py`: the `_ITALIC`/`_BOLD` constants stay in
`extract.py` (they are PyMuPDF flag bits), everything else moves.

```python
"""Backend-neutral raw extraction types — the typed Stage A product.

These are transient ingestion state, not the persisted IR (constitution #6:
domain/models.py carries the clean typed product). They live here rather than
in a backend module so that no aggregation and no candidate backend imports a
PDF library it does not use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from domain.models import BBox

# Some PDFs embed \t \r \xa0 runs inside their text spans; collapse each run to
# a single space at the source so no downstream consumer (block, chunk payload,
# unit) has to. \s is Unicode-aware, so it also folds the non-breaking space.
_WS_RUN = re.compile(r"\s+")


def norm_ws(text: str) -> str:
    return _WS_RUN.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Span:
    """One text run — text + bbox (PDF points, y-down from top-left) + font."""

    text: str
    bbox: BBox
    size: float
    font: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True, slots=True)
class TextLine:
    """One line. Its span order is the extractor's source order."""

    bbox: BBox
    spans: tuple[Span, ...]

    @property
    def text(self) -> str:
        return " ".join(span.text for span in self.spans)


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One text block. Layout may classify it but never reshape it."""

    bbox: BBox
    lines: tuple[TextLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def spans(self) -> tuple[Span, ...]:
        return tuple(span for line in self.lines for span in line.spans)


@dataclass(frozen=True, slots=True)
class PageExtract:
    """Raw extraction for one page. `raster` is produced on demand by a
    backend's `rasterize()` (transient, never persisted), not stored here."""

    page: int  # 0-based physical index
    width: float  # PDF points
    height: float
    spans: tuple[Span, ...]
    needs_ocr: bool  # no text layer but has image content (opt-in slow OCR pass)
    label: str  # printed page label, "" if none
    blocks: tuple[TextBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class RawExtraction:
    """Document-level Stage A output: per-page spans + doc metadata."""

    doc_id: str
    path: str
    title: str
    page_count: int
    toc: tuple[tuple[int, str, int], ...]  # (level, title, 1-based page)
    page_labels: tuple[str, ...]
    pages: tuple[PageExtract, ...]
    needs_ocr: bool  # any page lacked a text layer
```

- [ ] **Step 4: Repoint `extract.py` at the moved types**

In `sidecar-v3/ingest/extract.py`, delete the moved dataclasses and `_norm_ws`,
and replace them with:

```python
from ingest.raw import (
    PageExtract, RawExtraction, Span, TextBlock, TextLine, norm_ws as _norm_ws,
)
```

Keep `_ITALIC`, `_BOLD`, `_page_text_blocks`, `extract`, and `rasterize` in
place unchanged. The `_norm_ws` alias preserves the existing internal call
sites.

- [ ] **Step 5: Repoint the four importers**

```bash
cd /Users/jay/code/unseen-legend-lore
python3 - <<'EOF'
from pathlib import Path
edits = {
  "sidecar-v3/ingest/pdfium_extract.py":
    ("from ingest.extract import PageExtract, RawExtraction, Span, TextBlock, TextLine, _norm_ws",
     "from ingest.raw import PageExtract, RawExtraction, Span, TextBlock, TextLine, norm_ws as _norm_ws"),
  "sidecar-v3/ingest/pdfplumber_extract.py":
    ("from ingest.extract import PageExtract, RawExtraction, Span, TextBlock, TextLine",
     "from ingest.raw import PageExtract, RawExtraction, Span, TextBlock, TextLine"),
  "sidecar-v3/ingest/layout.py":
    ("from ingest.extract import PageExtract, RawExtraction, Span, TextBlock, rasterize",
     "from ingest.extract import rasterize\nfrom ingest.raw import PageExtract, RawExtraction, Span, TextBlock"),
  "sidecar-v3/ingest/pipeline.py":
    ("from ingest.extract import RawExtraction, extract",
     "from ingest.extract import extract\nfrom ingest.raw import RawExtraction"),
}
for path, (old, new) in edits.items():
    p = Path(path); t = p.read_text()
    assert t.count(old) == 1, path
    p.write_text(t.replace(old, new))
    print("repointed", path)
EOF
```

- [ ] **Step 6: Run the raw half of the new test plus the full suite**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test, including the new `test_raw_imports_no_pdf_library`.
The suite must be green at every task boundary; the `ingest.blocks` half of this
test is added in Task 4, alongside the module it guards.

- [ ] **Step 7: Commit**

```bash
git add sidecar-v3/ingest/raw.py sidecar-v3/ingest/extract.py \
        sidecar-v3/ingest/pdfium_extract.py sidecar-v3/ingest/pdfplumber_extract.py \
        sidecar-v3/ingest/layout.py sidecar-v3/ingest/pipeline.py \
        sidecar-v3/tests/test_raw_is_backend_neutral.py
git commit -m "refactor(v3/ingest): backend-neutral raw types so aggregation drops the PyMuPDF import"
```

---

### Task 3: Measure whether PDFium text objects give cell boundaries

A **measurement task**, not production code. Its deliverable is a committed
finding that decides how Task 4 segments cells. A table cell is usually its own
text-showing operator, so `FPDF_PAGEOBJ_TEXT` objects may supply cell boundaries
directly instead of inferring them from gaps.

**Files:**
- Create: `docs/roadmap/2026-08-29-pdfium-text-objects-finding.md`
- Scratch only (do not commit): a probe script.

**Interfaces:**
- Consumes: nothing.
- Produces: a decision consumed by Task 4 — either "text objects bound cells,
  use them" or "infer cells from the gap distribution".

- [ ] **Step 1: Probe the four worst table pages**

The pages where PDFium's `table_cells` collapsed hardest are g02 (osric_2e
p.40, 1.000 → 0.000), g06 (black_hack_1e p.4, 1.000 → 0.000), g15 (yze_srd
p.20, 1.000 → 0.000), and g37 (srd_5_2_1 p.34, 1.000 → 0.200).

```python
import json, sys
sys.path.insert(0, "sidecar-v3")
import pypdfium2, pypdfium2.raw as raw
import ctypes

m = json.load(open("evals/corpus.manifest.json"))
CASES = [("osric_2e", 39), ("black_hack_1e", 3), ("yze_srd", 19), ("srd_5_2_1", 33)]
for doc_id, idx in CASES:
    d = next(x for x in m["documents"] if x["id"] == doc_id)
    pdf = pypdfium2.PdfDocument("evals/corpus/" + d["pdf"]["path"])
    page = pdf[idx]
    tp = page.get_textpage()
    texts = []
    for obj in page.get_objects():
        if obj.type != raw.FPDF_PAGEOBJ_TEXT:
            continue
        n = raw.FPDFTextObj_GetText(obj.raw, tp.raw, None, 0)
        buf = ctypes.create_string_buffer(n)
        raw.FPDFTextObj_GetText(obj.raw, tp.raw,
                                ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), n)
        texts.append((obj.get_pos(), buf.raw.decode("utf-16-le").rstrip("\x00")))
    print(f"\n=== {doc_id} p{idx+1}: {len(texts)} text objects")
    for pos, txt in texts[:12]:
        print(f"   x0={pos[0]:7.1f} {txt[:60]!r}")
```

- [ ] **Step 2: Answer one question per page**

For each page, record: does one text object correspond to one table cell, or
does an object span a whole row? Compare against the PyMuPDF line output for
the same page, which is the cell-per-line reference.

- [ ] **Step 3: Write the finding**

Create `docs/roadmap/2026-08-29-pdfium-text-objects-finding.md` with a table of
the four pages, objects-per-row observed, and one of two verdicts stated
explicitly: **USE TEXT OBJECTS** (Task 4 takes cell boundaries from object
membership) or **INFER FROM GAPS** (Task 4 segments on the gap distribution).
Record the evidence either way — a NO answer is as useful as a YES and stops
the next person re-probing it.

- [ ] **Step 4: Commit**

```bash
git add docs/roadmap/2026-08-29-pdfium-text-objects-finding.md
git commit -m "spike(v3/ingest): do PDFium text objects bound table cells?"
```

---

### Task 4: Run → word → cell merging in `ingest/blocks.py`

The defect that costs PDFium 13 of its 18 regressions. The current adapter
splits a row only on gaps wider than `max(18.0, median_char_width * 6)` — an
absolute point threshold that merges an entire table row into one line. Gap
thresholds must be relative to the row's own type size.

**Files:**
- Create: `sidecar-v3/ingest/blocks.py`
- Test: `sidecar-v3/tests/test_blocks.py`

**Interfaces:**
- Consumes: `ingest.raw.Span`, `domain.models.BBox`.
- Produces: `TUNING: dict[str, float]`; `em(spans: Sequence[Span]) -> float`;
  `rows(spans: Sequence[Span], em: float) -> list[list[Span]]`;
  `cells(row: Sequence[Span], em: float) -> list[tuple[Span, ...]]` — each
  returned tuple is one cell's **words**. Task 5 consumes `cells`; Task 7
  consumes `build`.

**Each input Span is one PDFium text object, not one character.** Task 3
measured that a text object never contains glyphs from two table columns: 1:1
with PyMuPDF's cell-per-line output on three of four probe pages, and finer
than cells (608 objects to 423 lines, per-glyph kerning) on the fourth — never
coarser. Object membership is therefore a safe upper bound, and this module
**merges** atomic objects upward into words and cells. It never splits one.
That inversion is the whole point: splitting a character run on gap width is
what merges a table row into a single line today.

- [ ] **Step 1: Write the failing tests**

Create `sidecar-v3/tests/test_blocks.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.blocks'`

- [ ] **Step 3: Write the minimal implementation**

Create `sidecar-v3/ingest/blocks.py`:

```python
"""Aggregation: atomic text runs with geometry into a block hierarchy.

PDF has no block primitive. MuPDF synthesizes blocks in stext-device.c by
clustering characters into lines on baseline continuity and lines into blocks on
flow proximity; PyMuPDF exposes that heuristic, and W1 depends on it. This
module owns the equivalent aggregation for a permissively licensed backend.

Its input unit is one atomic run — a PDFium text object. Task 3 measured that
such an object never spans two table columns, so this module only ever merges
runs upward into words and cells; it never splits one. Splitting a run on gap
width is what collapses a table row into a single line.

Imports no PDF library — the run source is swappable without touching this.
"""
from __future__ import annotations

import statistics
from typing import Sequence

from domain.models import BBox
from ingest.raw import Span, norm_ws

# Tunable constants, expressed as multiples of the row's em (its type size) so
# they scale with the page instead of assuming one. Per the plan's
# anti-overfitting rule these may be tuned ONLY against the ten section 4.3
# fixture pages; the 40-page golden set is the gate, never the tuning set.
TUNING = {
    "word_gap_em": 0.18,   # gap wider than this * em starts a new word
    "cell_gap_em": 1.20,   # gap wider than this * em starts a new cell
    "row_tol_em": 0.45,    # baseline clustering tolerance
}


def em(spans: Sequence[Span]) -> float:
    """The type size, taken as the median run height."""
    return statistics.median(s.bbox.y1 - s.bbox.y0 for s in spans)


def rows(spans: Sequence[Span], em_: float) -> list[list[Span]]:
    """Group runs into baseline rows, ordered top to bottom."""
    tol = max(2.0, em_ * TUNING["row_tol_em"])
    out: list[list[Span]] = []
    for span in sorted(spans, key=lambda s: ((s.bbox.y0 + s.bbox.y1) / 2, s.bbox.x0)):
        centre = (span.bbox.y0 + span.bbox.y1) / 2
        row = next((r for r in out
                    if abs(centre - sum((s.bbox.y0 + s.bbox.y1) / 2 for s in r) / len(r)) <= tol),
                   None)
        if row is None:
            out.append([span])
        else:
            row.append(span)
    for row in out:
        row.sort(key=lambda s: s.bbox.x0)
    return out


def _join(parts: list[Span]) -> Span:
    """Concatenate abutting runs into one word. Runs carry their own trailing
    spaces, so norm_ws collapses the seams."""
    return Span(
        norm_ws("".join(p.text for p in parts)),
        BBox(min(p.bbox.x0 for p in parts), min(p.bbox.y0 for p in parts),
             max(p.bbox.x1 for p in parts), max(p.bbox.y1 for p in parts)),
        round(statistics.median(p.size for p in parts), 2),
        parts[0].font, parts[0].bold, parts[0].italic,
    )


def cells(row: Sequence[Span], em_: float) -> list[tuple[Span, ...]]:
    """Merge one baseline row's runs into cells, each a tuple of words.

    Runs are atomic — a PDFium text object never spans two columns, so a cell
    boundary is always a run boundary. Two thresholds decide how far to merge:
    a gap under word_gap joins two runs into one word (pages that split words
    mid-glyph), a gap under cell_gap keeps them in the same cell, anything
    wider starts a new cell. Nothing here ever splits a run.
    """
    word_gap, cell_gap = em_ * TUNING["word_gap_em"], em_ * TUNING["cell_gap_em"]
    out: list[tuple[Span, ...]] = []
    words: list[Span] = []
    parts: list[Span] = []
    for span in row:
        if parts:
            gap = span.bbox.x0 - parts[-1].bbox.x1
            if gap > cell_gap:
                words.append(_join(parts))
                out.append(tuple(words))
                words, parts = [], []
            elif gap > word_gap:
                words.append(_join(parts))
                parts = []
        parts.append(span)
    if parts:
        words.append(_join(parts))
    if words:
        out.append(tuple(words))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py sidecar-v3/tests/test_raw_is_backend_neutral.py -q`
Expected: PASS — all five `test_blocks` tests plus both neutrality tests.

- [ ] **Step 5: Guard the new module's backend neutrality**

Append to `sidecar-v3/tests/test_raw_is_backend_neutral.py`:

```python
def test_blocks_imports_no_pdf_library():
    assert not PDF_LIBS_IN(_imported_modules("ingest.blocks"))
```

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test. A failure here means `blocks.py` picked up a PDF
library import; remove it rather than relaxing the test.

- [ ] **Step 6: Commit**

```bash
git add sidecar-v3/ingest/blocks.py sidecar-v3/tests/test_blocks.py \
        sidecar-v3/tests/test_raw_is_backend_neutral.py
git commit -m "feat(v3/ingest): em-relative word and cell segmentation"
```

---

### Task 5: Column bands and block assembly

**Files:**
- Modify: `sidecar-v3/ingest/blocks.py`
- Test: `sidecar-v3/tests/test_blocks.py`

**Interfaces:**
- Consumes: `em`, `rows`, `cells` from Task 4.
- Produces: `bands(spans, width, em_) -> list[tuple[float, float]]` and
  `build(spans: Sequence[Span], width: float, height: float) -> tuple[TextBlock, ...]`.
  Task 6 calls `build` only.

- [ ] **Step 1: Write the failing tests**

Append to `sidecar-v3/tests/test_blocks.py`:

```python
from ingest.blocks import bands, build

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: FAIL — `ImportError: cannot import name 'bands' from 'ingest.blocks'`

- [ ] **Step 3: Write the minimal implementation**

Add to `TUNING` in `sidecar-v3/ingest/blocks.py`:

```python
    "gutter_min_em": 1.50,    # narrowest zero-coverage x-run that can be a gutter
    "gutter_cover": 0.60,     # fraction of rows a gutter must stay clear across
    "block_gap_lines": 1.60,  # vertical gap > this * median line pitch splits a block
```

Append to the module:

```python
def bands(spans: Sequence[Span], width: float, em_: float) -> list[tuple[float, float]]:
    """Column bands, found as maximal x-runs no character crosses.

    Deliberately geometric: the layout model misses 50-65% of spans on dense
    pages, so it can classify columns but must never define them.
    """
    covered = [False] * (int(width) + 1)
    for span in spans:
        for x in range(max(0, int(span.bbox.x0)), min(int(width), int(span.bbox.x1)) + 1):
            covered[x] = True
    if not any(covered):
        return [(0.0, width)]
    first, last = covered.index(True), len(covered) - 1 - covered[::-1].index(True)
    min_gutter = em_ * TUNING["gutter_min_em"]
    out: list[tuple[float, float]] = []
    start, run = first, 0
    for x in range(first, last + 2):
        if x <= last and not covered[x]:
            run += 1
            continue
        if run >= min_gutter and start < x - run:
            out.append((float(start), float(x - run)))
            start = x
        run = 0
    out.append((float(start), float(last + 1)))
    return out or [(float(first), float(last + 1))]


def _band_of(span: Span, found: list[tuple[float, float]]) -> int:
    centre = (span.bbox.x0 + span.bbox.x1) / 2
    for i, (x0, x1) in enumerate(found):
        if x0 <= centre <= x1:
            return i
    return min(range(len(found)),
               key=lambda i: min(abs(centre - found[i][0]), abs(centre - found[i][1])))


def build(spans: Sequence[Span], width: float, height: float) -> tuple[TextBlock, ...]:
    """Atomic runs with geometry into blocks: bands, then rows, then cells.

    Reading order is band order, then top to bottom. Nothing merges across a
    band, and no line merges across a cell boundary.
    """
    if not spans:
        return ()
    em_ = em(spans)
    found = bands(spans, width, em_)
    out: list[TextBlock] = []
    for index in range(len(found)):
        in_band = [s for s in spans if _band_of(s, found) == index]
        if not in_band:
            continue
        for row in rows(in_band, em_):
            for cell in cells(row, em_):
                if not cell:
                    continue
                box = BBox(min(w.bbox.x0 for w in cell), min(w.bbox.y0 for w in cell),
                           max(w.bbox.x1 for w in cell), max(w.bbox.y1 for w in cell))
                out.append(TextBlock(box, (TextLine(box, cell),)))
    return tuple(out)
```

Add `TextBlock, TextLine` to the `ingest.raw` import at the top of the module.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: PASS — all ten tests.

- [ ] **Step 5: Commit**

```bash
git add sidecar-v3/ingest/blocks.py sidecar-v3/tests/test_blocks.py
git commit -m "feat(v3/ingest): geometric column bands with conservation and no-straddle invariants"
```

---

### Task 6: Group prose rows into multi-line blocks

`build()` currently emits one `TextBlock` per cell, so every block holds exactly
one line. That is the same structural deficiency that disqualified the earlier
pdfplumber adapter: no block hierarchy, so the W1 layout contract has nothing to
classify above line level. The PyMuPDF reference this work is gated against
groups a paragraph's lines into one block, and `TUNING["block_gap_lines"]` was
added for this stage but is not yet read.

The rule is geometric and needs no layout model. Within a band, a row that holds
exactly one cell is prose and joins the paragraph above it when the leading is
normal; a row holding several cells is a table row, and each of its cells stays
its own single-line block so cell atomicity survives.

**Files:**
- Modify: `sidecar-v3/ingest/blocks.py`
- Test: `sidecar-v3/tests/test_blocks.py`

**Interfaces:**
- Consumes: `rows`, `cells`, `TUNING` from Tasks 4 and 5.
- Produces: no signature change — `build(spans, width, height)` keeps its
  contract and its two invariants. Internally it delegates each band to a new
  `_blocks_in_band(band_rows, em_) -> list[TextBlock]`.

- [ ] **Step 1: Write the failing tests**

Append to `sidecar-v3/tests/test_blocks.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: FAIL — `test_consecutive_prose_rows_become_one_block` reports 3 blocks
where 1 is expected, because `build()` emits one block per cell today.

- [ ] **Step 3: Implement the grouping**

Replace `build()`'s per-band inner loop with a call to a new helper. Add to
`sidecar-v3/ingest/blocks.py`:

```python
def _bbox(spans: Sequence[Span]) -> BBox:
    return BBox(min(s.bbox.x0 for s in spans), min(s.bbox.y0 for s in spans),
                max(s.bbox.x1 for s in spans), max(s.bbox.y1 for s in spans))


def _pitch(band_rows: Sequence[Sequence[Span]]) -> float:
    """Median centre-to-centre distance between consecutive rows — the band's
    own leading, so the block-splitting threshold scales with the page."""
    centres = [sum((s.bbox.y0 + s.bbox.y1) / 2 for s in row) / len(row) for row in band_rows]
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    return statistics.median(gaps) if gaps else 0.0


def _blocks_in_band(band_rows: Sequence[Sequence[Span]], em_: float) -> list[TextBlock]:
    """Rows into blocks. A row of one cell is prose and joins the paragraph
    above it while the leading stays normal; a row of several cells is a table
    row whose cells each stay their own block, so cell atomicity survives."""
    limit = (_pitch(band_rows) or em_) * TUNING["block_gap_lines"]
    out: list[TextBlock] = []
    para: list[TextLine] = []

    def flush() -> None:
        if para:
            out.append(TextBlock(_bbox([s for line in para for s in line.spans]), tuple(para)))
            para.clear()

    for row in band_rows:
        row_cells = cells(row, em_)
        lines = [TextLine(_bbox(cell), cell) for cell in row_cells]
        if len(lines) == 1:
            if para and lines[0].bbox.y0 - para[-1].bbox.y1 > limit:
                flush()
            para.append(lines[0])
        else:
            flush()
            out.extend(TextBlock(line.bbox, (line,)) for line in lines)
    flush()
    return out
```

Then in `build()`, replace the `for row in rows(in_band, em_):` body with:

```python
        out.extend(_blocks_in_band(rows(in_band, em_), em_))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: PASS — all fifteen tests, including the conservation and no-straddle
invariants from Task 5, which must still hold.

- [ ] **Step 5: Remove the dead tuning key**

`TUNING["gutter_cover"]` is never read: `bands()` requires an x-run no span
crosses anywhere on the page, which is strictly stronger than covering a
fraction of the page height. Delete the key and its comment rather than leaving
configuration that does nothing.

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test.

- [ ] **Step 6: Commit**

```bash
git add sidecar-v3/ingest/blocks.py sidecar-v3/tests/test_blocks.py
git commit -m "feat(v3/ingest): group prose rows into multi-line blocks"
```

---

### Task 7: Rewire the PDFium adapter onto text objects and `blocks.build()`

**Files:**
- Modify: `sidecar-v3/ingest/pdfium_extract.py`
- Modify: `sidecar-v3/tests/test_pdfium_extract.py`

**Interfaces:**
- Consumes: `ingest.blocks.build`.
- Produces: `_span(text, bounds, height, font, weight, italic_angle) -> Span | None`
  (pure — converts one text object's raw values into a Span, or None if the
  object carries nothing renderable) and `_objects(page, text_page) -> tuple[Span, ...]`
  (walks PDFium). `extract(pdf_path, doc_id=None) -> RawExtraction` gains real
  blocks. Task 11 gates it.

The split is deliberate: `_span` holds all the convention logic and is unit
testable with plain values, while `_objects` needs real PDFium handles and is
covered by corpus-backed integration tests.

**Three PDFium facts, verified against the installed pypdfium2 5.13.0 — do not
rediscover them:**
1. `PdfObject` has **no** `get_pos()`. Bounds come from `obj.get_bounds()`,
   returning `(left, bottom, right, top)` with y measured **up** from the page
   bottom. `BBox` and every consumer use PyMuPDF's y-down top-left origin.
2. `obj.type` works (a runtime instance attribute). `raw.FPDF_PAGEOBJ_TEXT == 1`.
   `page.get_objects()` already recurses into form XObjects.
3. `FPDFTextObj_GetFontSize` returns the **unscaled** text-space size — 1.0 on
   real pages, because the scale lives in the object's matrix. Do not use it for
   `Span.size`; take the size from the bounds height, as the previous adapter
   did. Font name comes from `FPDFFont_GetBaseFontName(FPDFTextObj_GetFont(obj))`,
   weight from `FPDFFont_GetWeight` (bold at >= 700), and slant from
   `FPDFFont_GetItalicAngle`, which writes the angle through an `int*` out-param
   and returns a success flag — read the out-param, not the return value.

- [ ] **Step 1: Write the failing tests**

Replace the body of `sidecar-v3/tests/test_pdfium_extract.py` with:

```python
"""The PDFium adapter is thin: one Span per text object, all aggregation in
ingest.blocks. These tests pin the seam, not the aggregation."""
from domain.models import BBox
from ingest.pdfium_extract import _span

PAGE_HEIGHT = 100.0
BOUNDS = (10.0, 80.0, 40.0, 90.0)  # PDFium: (left, bottom, right, top), y-up


def test_span_reports_top_left_origin_boxes():
    """PDFium measures y up from the bottom; BBox and every consumer of it use
    PyMuPDF's y-down top-left origin, the layout raster included."""
    got = _span("Gambeson", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0)
    assert got.bbox == BBox(10.0, 10.0, 40.0, 20.0)


def test_span_size_comes_from_the_bounds_not_the_font_size():
    """FPDFTextObj_GetFontSize returns the unscaled text-space size (1.0 on real
    pages); the rendered size is the height of the object's bounds."""
    assert _span("Gambeson", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).size == 10.0


def test_span_keeps_the_whole_object_as_one_run():
    """Objects are atomic — the adapter must not pre-split or pre-group them."""
    assert _span("2 Armor Points", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).text == "2 Armor Points"


def test_span_normalises_internal_whitespace():
    assert _span("Find\tT raps ", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).text == "Find T raps"


def test_span_preserves_ligature_codepoints():
    """A ligature is one rendered glyph; dropping it corrupts words like 'find'."""
    assert _span("\ufb01nd", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0).text == "\ufb01nd"


def test_span_reads_bold_from_weight_and_italic_from_angle():
    bold = _span("x", BOUNDS, PAGE_HEIGHT, "Serif", 700, 0)
    slanted = _span("x", BOUNDS, PAGE_HEIGHT, "Serif", 400, -12)
    assert (bold.bold, bold.italic) == (True, False)
    assert (slanted.bold, slanted.italic) == (False, True)


def test_span_is_none_for_empty_or_degenerate_objects():
    assert _span("   ", BOUNDS, PAGE_HEIGHT, "Serif", 400, 0) is None
    assert _span("x", (10.0, 80.0, 10.0, 90.0), PAGE_HEIGHT, "Serif", 400, 0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_extract.py -q`
Expected: FAIL — `ImportError: cannot import name '_span' from 'ingest.pdfium_extract'`

- [ ] **Step 3: Rewrite the adapter**

In `sidecar-v3/ingest/pdfium_extract.py`, delete `_line_spans`, `_words`,
`_word`, and `_page_blocks` — `blocks.build()` replaces all four — and add
`_span` and `_objects`. `_span` takes the raw values listed in the Interfaces
block and returns a `Span` in y-down space with `size` from the bounds height,
`text` passed through `norm_ws`, `bold` from `weight >= 700`, and `italic` from
a non-zero italic angle; it returns `None` when the normalised text is empty or
the bounds are degenerate. `_objects` walks `page.get_objects()`, keeps
`obj.type == raw.FPDF_PAGEOBJ_TEXT`, reads each object's text with
`FPDFTextObj_GetText` (call once with length 0 to size the buffer, decode
UTF-16LE, strip the NUL terminator), reads its font values per fact 3 above,
calls `_span`, and drops the Nones.

Change the page loop inside `extract` to:

```python
        width, height = page.get_size()
        text_page = page.get_textpage()
        blocks = build(_objects(page, text_page), width, height)
        spans = tuple(span for block in blocks for span in block.spans)
```

Update the imports: drop `statistics`, add `import ctypes`,
`import pypdfium2.raw as pdfium_raw`, and `from ingest.blocks import build`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_extract.py -q`
Expected: PASS — all seven tests.

- [ ] **Step 5: Write the failing integration tests**

`_objects` and rasterization need real PDFium handles, so these run against the
corpus and skip when it is absent. Append to the same test file:

```python
import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[2] / "evals" / "corpus.manifest.json"


def _corpus_pdf(doc_id: str) -> Path:
    if not MANIFEST.exists():
        pytest.skip("corpus manifest absent")
    doc = next(d for d in json.loads(MANIFEST.read_text())["documents"] if d["id"] == doc_id)
    path = MANIFEST.parent / "corpus" / doc["pdf"]["path"]
    if not path.exists():
        pytest.skip("corpus PDF absent")
    return path


def test_objects_carry_text_font_and_weight():
    """layout.py builds FontStats from these fields to classify headings; an
    adapter that leaves them empty cannot reach the reference."""
    import pypdfium2
    from ingest.pdfium_extract import _objects

    page = pypdfium2.PdfDocument(str(_corpus_pdf("osric_2e")))[155]
    spans = _objects(page, page.get_textpage())
    assert spans, "no text objects found on a text-bearing page"
    assert any(span.font for span in spans)
    assert any(span.bold for span in spans)
    assert all(span.size > 0 and span.text.strip() for span in spans)


def test_no_object_spans_two_columns_on_a_two_column_page():
    """The property the whole design rests on (Task 3 finding). OSRIC p.156 is
    a dense two-column page; its gutter sits near the page mid-line."""
    import pypdfium2
    from ingest.pdfium_extract import _objects

    page = pypdfium2.PdfDocument(str(_corpus_pdf("osric_2e")))[155]
    width = page.get_size()[0]
    straddlers = [s.text for s in _objects(page, page.get_textpage())
                  if s.bbox.x0 < width * 0.45 < s.bbox.x1 and s.bbox.x1 > width * 0.55]
    assert not straddlers, f"objects crossing the gutter: {straddlers[:5]}"


def test_rasterize_returns_rgb_pixels():
    from ingest.pdfium_extract import rasterize

    raster = rasterize(str(_corpus_pdf("cairn_1e")), 9, dpi=150)
    assert raster.ndim == 3 and raster.shape[2] == 3
    assert raster.dtype.name == "uint8"
```

- [ ] **Step 6: Run them**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_extract.py -q`
Expected: PASS. If `test_objects_carry_text_font_and_weight` finds empty font
names, check the `FPDFFont_GetBaseFontName` buffer sizing before changing the
assertion. If `test_no_object_spans_two_columns_on_a_two_column_page` fails, stop
and report — that property is what Task 4's design depends on, and a failure
means the Task 3 finding does not generalise.

- [ ] **Step 7: Run the full suite**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test.

- [ ] **Step 8: Commit**

```bash
git add sidecar-v3/ingest/pdfium_extract.py sidecar-v3/tests/test_pdfium_extract.py
git commit -m "refactor(v3/ingest): one Span per PDFium text object, aggregation in ingest.blocks"
```

---

### Task 8: Order table rows row-major, page columns band-major

The diagnostic gate run after Task 7 scored `table_cells` **0.408** against a
0.982 reference, with 14 of 18 regressions on table pages, while
`content_recall` reached 0.988. All the text is present; the order is wrong.

`bands()` uses a global x-projection, which cannot tell a page-column gutter
from the gap between a table's own columns. On black_hack_1e p.4 it finds four
bands — `ITEM`, `COST`, `USAGE DIE`, `NOTES` — and `build()`, iterating bands
outermost, emits each entire column as one block:

```
'ITEM\nGambeson\nLeather\nChain Mail…'
'COST\n50\n100\n350…'
```

The golden `cells` expectations are whole rows (`'gambeson 50 2 armor points'`,
`'80 25 10 20 20 30 35'`), so `table_cells` is really measuring row coherence.
Column-major emission destroys it. MuPDF never hits this because it groups
locally by text flow rather than by a global projection.

**The discriminator is baseline alignment.** In a table, cells in adjacent
columns share row baselines. In two-column prose, the columns have independent
baselines — a left-column line almost never shares a baseline with a
right-column line. So adjacent bands whose rows align are one table and must be
read row-major; adjacent bands whose rows do not align are page columns and must
be read band-major.

**Files:**
- Modify: `sidecar-v3/ingest/blocks.py`
- Test: `sidecar-v3/tests/test_blocks.py`

**Interfaces:**
- Consumes: `bands`, `rows`, `cells`, `_blocks_in_band` from Tasks 4-6.
- Produces: no signature change. `build()` keeps its contract and both
  invariants. Internally it groups adjacent aligned bands and orders those
  row-major.

- [ ] **Step 1: Write the failing tests**

Append to `sidecar-v3/tests/test_blocks.py`:

```python
def _table_page() -> list[Span]:
    """Three rows x two columns on shared baselines — a table."""
    out = []
    for i, y in enumerate((0.0, 20.0, 40.0)):
        out.append(_obj(f"item{i}", 20.0, y=y, width=80.0))
        out.append(_obj(f"cost{i}", 200.0, y=y, width=60.0))
    return out


def _two_column_prose() -> list[Span]:
    """Two prose columns on deliberately unaligned baselines."""
    out = []
    for i, y in enumerate((0.0, 14.0, 28.0)):
        out.append(_obj(f"left{i}", 20.0, y=y, width=120.0))
    for i, y in enumerate((7.0, 21.0, 35.0)):
        out.append(_obj(f"right{i}", 240.0, y=y, width=120.0))
    return out


def test_a_table_reads_row_major():
    """Golden cell expectations are whole rows, so a row's cells must stay
    contiguous and in order."""
    text = " ".join(b.text for b in build(_table_page(), PAGE_W, PAGE_H))
    assert "item0 cost0" in text, text
    assert "item1 cost1" in text, text


def test_two_column_prose_still_reads_band_major():
    """The failure this whole design exists to prevent: a left-column line
    followed by a right-column line at the same height."""
    text = " ".join(b.text for b in build(_two_column_prose(), PAGE_W, PAGE_H))
    assert text.index("left2") < text.index("right0"), text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: `test_a_table_reads_row_major` FAILS — the text reads
`item0 item1 item2 cost0 cost1 cost2`. `test_two_column_prose_still_reads_band_major`
should already PASS; if it does not, say so before changing anything.

- [ ] **Step 3: Implement the discriminator**

Add a `TUNING` key `"row_align_frac": 0.60` with a comment saying it is the
fraction of a band's rows that must share a baseline with the neighbouring band
before the two are read as one table.

Add a helper that decides whether two adjacent bands are row-aligned: take each
band's row centres (reuse `rows()`), and compute the fraction of the smaller
band's centres that fall within `row_tol_em * em` of some centre in the other.
Aligned when that fraction is at least `row_align_frac`.

Then in `build()`, partition the bands into runs of mutually aligned
neighbours. For a run of one band, emit `_blocks_in_band` as today. For a run of
two or more, emit row-major: walk the run's rows by y, and within each row emit
that row's cells left to right across the whole run, one block per cell. Never
merge spans from different bands into one block — the no-straddle invariant
still holds.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: PASS — every test, including conservation, no-straddle, the gutter
test, and the paragraph-grouping tests from Task 6.

- [ ] **Step 5: Re-run the diagnostic gate**

```bash
uv run --frozen --project sidecar-v3 python -m evals.run_eval \
  --engine v3 --suite extraction --pdf-backend pdfium --no-write \
  --gate evals/baselines/2026-08-29-v3-w1-reference.json
```

Record the by-kind table in your report. The number to beat is `table_cells`
0.408 with 18 regressions; the reference is 0.982 with 0. Do **not** tune any
`TUNING` constant to chase this number — report what you get.

- [ ] **Step 6: Commit**

```bash
git add sidecar-v3/ingest/blocks.py sidecar-v3/tests/test_blocks.py
git commit -m "fix(v3/ingest): read aligned bands row-major so table rows stay coherent"
```

---

### Task 9: Emit table rows as single blocks, matching the reference shape

Task 8 confirmed `build()` orders table cells row-major, yet the gate barely
moved (`table_cells` 0.408 → 0.439) because `layout.py`'s `_xy_cut` partitions
blocks at a fixed page midpoint and tears a wide table row apart again. It also
cost two real two-column pages (g34/g35, `reading_order` 1.000 → 0.619), because
the baseline-alignment discriminator misfires on books that share a baseline grid
across columns.

**The reference shows the shape to aim for.** On `black_hack_1e` p.4, PyMuPDF
emits one block per table *row*, spanning the full table width, with each cell a
line inside it:

```
x0=40.0 x1=342.4  'Gambeson | 50 | - | 2 Armor Points'
x0=40.0 x1=342.3  'Leather | 100 | - | 4 Armor Points'
```

An atomic row survives `_xy_cut` and makes the whole-row golden expectations
matchable. Our model is inverted — blocks as paragraphs of lines, where the
reference uses blocks as rows of cells.

**The discriminator, measured rather than assumed.** Gap width does not separate
tables from page columns; the distributions overlap (table 2.99-24.52 em, prose
2.65-36.22 em). Row *fill ratio* does — the fraction of a row's horizontal extent
actually covered by text:

| page kind | median fill | p25 |
|---|---:|---:|
| table (black_hack p.4, srd_5_2_1 p.34, cairn_1e p.11) | 0.24 / 0.48 / 0.27 | 0.18 / 0.39 / 0.22 |
| two-column prose (osric p.156, p.163, srd_5_1 p.103) | 0.95 / 0.95 / 0.87 | 0.95 / 0.93 / 0.82 |

Decide per **run** of consecutive multi-cell rows, not per row: a paragraph's
short final line has a low fill on its own, and the run median absorbs it.

**Files:**
- Modify: `sidecar-v3/ingest/blocks.py`
- Test: `sidecar-v3/tests/test_blocks.py`

**Interfaces:**
- Consumes: `bands`, `rows`, `cells`, `_blocks_in_band`, `_bbox` from Tasks 4-6.
- Produces: no signature change on `build()`. Removes the band-major global
  ordering and the baseline-alignment helper added in Task 8.

- [ ] **Step 1: Write the failing tests**

Append to `sidecar-v3/tests/test_blocks.py`:

```python
def test_a_table_row_is_one_block_with_a_line_per_cell():
    """The reference shape: an atomic row survives downstream reordering, which
    is what makes whole-row expectations matchable."""
    blocks = build(_table_page(), PAGE_W, PAGE_H)
    row0 = [b for b in blocks if "item0" in b.text][0]
    assert [line.text for line in row0.lines] == ["item0", "cost0"]
    assert row0.text.replace("\n", " ") == "item0 cost0"


def test_two_column_prose_rows_never_share_a_block():
    """Prose rows fill their column, so they must stay per-column blocks even
    though they sit at the same height."""
    for block in build(_two_column_prose(), PAGE_W, PAGE_H):
        assert not ("left" in block.text and "right" in block.text), block.text
```

Task 8 added `_table_page()` and `_two_column_prose()` helpers — reuse them. If
Task 8's `_two_column_prose` offsets its right column's baselines, remove that
offset so both columns share baselines: the fill-ratio discriminator must handle
the shared-baseline-grid case that broke g34/g35.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_blocks.py -q`
Expected: `test_a_table_row_is_one_block_with_a_line_per_cell` FAILS — each cell
is its own block today.

- [ ] **Step 3: Implement**

Replace `TUNING["row_align_frac"]` from Task 8 with `"row_fill_table": 0.70` —
the fill ratio below which a run of multi-cell rows is a table. 0.70 sits
between the tables' p75 (0.55) and the prose pages' p25 (0.82).

Delete Task 8's baseline-alignment helper and its band-run partitioning. In
`build()`:

1. Compute `rows()` over the whole page.
2. Partition into maximal runs of consecutive rows that segment into two or more
   cells.
3. For each run, take the median fill ratio — for a row, the sum of its cells'
   widths over the distance from its first cell's left edge to its last cell's
   right edge.
4. A run whose median fill is below `row_fill_table` is a table: emit one
   `TextBlock` per row, its lines being that row's cells left to right, its bbox
   the union.
5. Every other row belongs to a column: assign it to a band via the existing
   `bands()`/`_band_of()`, and emit `_blocks_in_band` per band as before.

Emit blocks sorted by `(bbox.y0, bbox.x0)`. Do **not** re-impose band-major
global ordering — `layout.py`'s `_xy_cut` owns reading order, and it is the same
code path that gives the PyMuPDF reference 0.982.

Conservation and no-straddle must still hold. Note that no-straddle now means no
block crosses a *page-column* boundary; a table row block legitimately spans the
table's own columns.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test.

- [ ] **Step 5: Re-run the diagnostic gate**

```bash
uv run --frozen --project sidecar-v3 python -m evals.run_eval \
  --engine v3 --suite extraction --pdf-backend pdfium --no-write \
  --gate evals/baselines/2026-08-29-v3-w1-reference.json
```

Numbers to beat: `table_cells` 0.439, `reading_order` 0.937, 18 regressions.
Reference is 0.982 / 1.000 / 0. Report what you get verbatim. Do **not** tune any
constant to chase it — `row_fill_table` was set from measured distributions and
stays at 0.70 for this run.

Also confirm g34 and g35 `reading_order` are back to 1.000; they are the
regression Task 8 introduced.

- [ ] **Step 6: Commit**

```bash
git add sidecar-v3/ingest/blocks.py sidecar-v3/tests/test_blocks.py
git commit -m "fix(v3/ingest): a table row is one block, matching the reference shape"
```

---

### Task 10: Document metadata — title, TOC, printed page labels

Both dead adapters returned an empty `toc` and empty `page_labels`; the v3
storage schema persists both. Spec section 6 makes metadata a gate row.

**Files:**
- Create: `sidecar-v3/ingest/pdfium_meta.py`
- Modify: `sidecar-v3/ingest/pdfium_extract.py`
- Test: `sidecar-v3/tests/test_pdfium_meta.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `title(pdf, fallback: str) -> str`,
  `toc(pdf) -> tuple[tuple[int, str, int], ...]`,
  `page_labels(pdf, page_count: int) -> tuple[str, ...]`, all taking an open
  `pypdfium2.PdfDocument`.

- [ ] **Step 1: Write the failing test**

Create `sidecar-v3/tests/test_pdfium_meta.py`:

```python
"""Metadata parity against the PyMuPDF reference on real corpus documents.
Skipped when the corpus is absent (it is gitignored)."""
import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[2] / "evals" / "corpus.manifest.json"


def _pdf(doc_id: str) -> Path:
    if not MANIFEST.exists():
        pytest.skip("corpus manifest absent")
    entry = json.loads(MANIFEST.read_text())
    doc = next(d for d in entry["documents"] if d["id"] == doc_id)
    path = MANIFEST.parent / "corpus" / doc["pdf"]["path"]
    if not path.exists():
        pytest.skip("corpus PDF absent")
    return path


@pytest.mark.parametrize("doc_id", ["osric_2e", "srd_5_1", "cairn_1e"])
def test_toc_matches_pymupdf(doc_id):
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import toc

    path = _pdf(doc_id)
    with pymupdf.open(str(path)) as doc:
        expected = tuple((lvl, title, page) for lvl, title, page in doc.get_toc())
    assert toc(pypdfium2.PdfDocument(str(path))) == expected


@pytest.mark.parametrize("doc_id", ["osric_2e", "srd_5_1"])
def test_page_labels_match_pymupdf(doc_id):
    import pymupdf, pypdfium2
    from ingest.pdfium_meta import page_labels

    path = _pdf(doc_id)
    with pymupdf.open(str(path)) as doc:
        expected = tuple(doc.load_page(i).get_label() or "" for i in range(doc.page_count))
    pdf = pypdfium2.PdfDocument(str(path))
    assert page_labels(pdf, len(pdf)) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_meta.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.pdfium_meta'`

- [ ] **Step 3: Implement against PDFium's outline and label APIs**

`FPDF_GetPageLabel` returns the printed label directly, so no `/PageLabels`
number-tree walk is needed. Create `sidecar-v3/ingest/pdfium_meta.py`:

```python
"""Document metadata from PDFium: title, outline, printed page labels.

The v3 storage schema persists toc and page_labels, so an adapter that returns
them empty fails the metadata gate (spec section 6).
"""
from __future__ import annotations

import ctypes

import pypdfium2.raw as raw


def _utf16(fn, *args) -> str:
    n = fn(*args, None, 0)
    if n <= 0:
        return ""
    buf = ctypes.create_string_buffer(n)
    fn(*args, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), n)
    return buf.raw.decode("utf-16-le").rstrip("\x00")


def title(pdf, fallback: str) -> str:
    return _utf16(raw.FPDF_GetMetaText, pdf.raw, b"Title") or fallback


def toc(pdf) -> tuple[tuple[int, str, int], ...]:
    """(level, title, 1-based page), matching PyMuPDF's get_toc().

    pypdfium2 reports a 0-based level and a 0-based destination page index;
    PyMuPDF reports both 1-based.
    """
    out: list[tuple[int, str, int]] = []
    for bookmark in pdf.get_toc():
        dest = bookmark.get_dest()
        page = (dest.get_index() if dest is not None else None)
        out.append((bookmark.level + 1, bookmark.get_title() or "",
                    (page + 1) if page is not None else -1))
    return tuple(out)


def page_labels(pdf, page_count: int) -> tuple[str, ...]:
    return tuple(_utf16(raw.FPDF_GetPageLabel, pdf.raw, i) for i in range(page_count))
```

If `test_toc_matches_pymupdf` shows a systematic off-by-one in level or page,
correct it here rather than relaxing the assertion — the two libraries'
conventions are the whole point of the test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_meta.py -q`
Expected: PASS on all five parametrised cases.

If a case cannot be made to pass, that is a spec section 6 metadata gate
failure. Stop and record which field on which document, rather than weakening
the test.

- [ ] **Step 5: Wire it into the adapter**

In `sidecar-v3/ingest/pdfium_extract.py`, replace the placeholder metadata in
the `RawExtraction` construction — currently `did` for the title, `()` for
`toc`, and `tuple("" for _ in pages)` for `page_labels` — with calls to
`pdfium_meta.title`, `.toc`, and `.page_labels`, and set each `PageExtract`'s
`label` from the corresponding entry.

- [ ] **Step 6: Run the full suite**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test.

- [ ] **Step 7: Commit**

```bash
git add sidecar-v3/ingest/pdfium_meta.py sidecar-v3/ingest/pdfium_extract.py \
        sidecar-v3/tests/test_pdfium_meta.py
git commit -m "feat(v3/ingest): title, outline, and printed page labels from PDFium"
```

---

### Task 11: Gate the candidate and record the verdict

**Files:**
- Modify: `docs/roadmap/2026-08-28-permissive-pdf-backend-plan.md`
- Create: `evals/baselines/` outputs (written by the runs)

**Interfaces:**
- Consumes: the adapter from Tasks 7-10.
- Produces: a Go/No-Go verdict recorded in the spec.

- [ ] **Step 1: Run the 40-page golden gate**

```bash
uv run --frozen --project sidecar-v3 python -m evals.run_eval \
  --engine v3 --suite extraction --pdf-backend pdfium --no-write \
  --gate evals/baselines/2026-08-29-v3-w1-reference.json
```

Expected on a GO: `no per-page regressions`, exit 0. Record the by-kind table
whatever the outcome. The reference is content 1.000 / order 1.000 / cells
0.982; the run this plan starts from is 0.972 / 0.958 / 0.549 with 18
regressions.

- [ ] **Step 2: Inspect the focused fixtures by eye**

```bash
uv run --frozen --project sidecar-v3 python -m evals.extraction.review \
  --engine v3 --doc osric_2e --pages 156,163 --open
```

Repeat for `cairn_1e --pages 10,11`, `srd_5_1 --pages 103,315`, and
`black_hack_1e --pages 4,6`. Aggregate scores are not sufficient evidence:
confirm no column merge, no torn stat line, no table corruption.

- [ ] **Step 3: Run corpus-wide QA with no writes**

```bash
uv run --frozen --project sidecar-v3 python -m evals.run_eval \
  --engine v3 --suite corpus-qa --pdf-backend pdfium --no-write
```

Expected: 0 empty pages; block recall and label integrity at least the W1
reference.

- [ ] **Step 4: Time a 400-page representative**

```bash
time uv run --frozen --project sidecar-v3 python -c "
import sys; sys.path.insert(0, 'sidecar-v3')
from ingest.pdfium_extract import extract
raw = extract('evals/corpus/basic_fantasy/Basic-Fantasy-RPG-Rules-r142.pdf')
print(raw.page_count, 'pages')"
```

Expected: extraction plus rasterization for a 400-page book inside the
15-minute indexing budget.

- [ ] **Step 5: Record the verdict**

Update section 2's results table and add a dated Go/No-Go line to
`docs/roadmap/2026-08-28-permissive-pdf-backend-plan.md`. On a NO-GO, state
which gate failed and which pages; do not tune ranking or alter the eval
specification to hide it.

- [ ] **Step 6: Commit**

```bash
git add docs/roadmap/2026-08-28-permissive-pdf-backend-plan.md evals/baselines/
git commit -m "eval(v3/ingest): PDFium block-builder verdict against the W1 reference"
```

---

## Out of Scope

- **P4 cutover.** Making PDFium the default, removing `pymupdf` from
  `sidecar-v3/pyproject.toml`, deleting the losing adapters, bumping the
  pipeline version, and reindexing all happen only after Task 11 returns a GO.
- **The v2 sidecar.** `pymupdf4llm` keeps `check-third-party.py --release` red
  regardless of this plan's outcome. Scope is v3 only, by decision.
- **The packaging gate.** Spec section 6's macOS/Windows release smoke path
  needs a real release build, so it is verified at P4 cutover, not here.
- **A line-based W1 contract.** If Task 11 fails with regressions concentrated on
  `two_column` pages, the block abstraction is wrong and that contingency opens
  as its own design with a retrieval regression pass — not as a patch here.

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
| `sidecar-v3/ingest/blocks.py` | **create** — all aggregation. `build(chars, width, height) -> tuple[TextBlock, ...]`. Imports no PDF library. |
| `sidecar-v3/ingest/pdfium_extract.py` | **modify** — thin: PDFium characters → `Span`s → `blocks.build()` → `RawExtraction`, plus document metadata. |
| `sidecar-v3/ingest/pdfium_meta.py` | **create** — title, TOC, and printed page labels from PDFium. |
| `sidecar-v3/tests/test_blocks.py` | **create** — segmentation and banding on synthetic geometry. |
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

### Task 4: Character → word → cell segmentation in `ingest/blocks.py`

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
  returned tuple is one cell's **words**. Task 5 consumes `cells`; Task 6
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
"""Aggregation: characters with geometry into a block hierarchy.

PDF has no block primitive. MuPDF synthesizes blocks in stext-device.c by
clustering characters into lines on baseline continuity and lines into blocks on
flow proximity; PyMuPDF exposes that heuristic, and W1 depends on it. This
module owns the equivalent aggregation for a permissively licensed backend.

Imports no PDF library — the word source is swappable without touching this.
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


def em(chars: Sequence[Span]) -> float:
    """The row's type size, taken as the median character height."""
    return statistics.median(c.bbox.y1 - c.bbox.y0 for c in chars)


def rows(chars: Sequence[Span], em_: float) -> list[list[Span]]:
    """Group characters into baseline rows, ordered top to bottom."""
    tol = max(2.0, em_ * TUNING["row_tol_em"])
    out: list[list[Span]] = []
    for char in sorted(chars, key=lambda c: ((c.bbox.y0 + c.bbox.y1) / 2, c.bbox.x0)):
        centre = (char.bbox.y0 + char.bbox.y1) / 2
        row = next((r for r in out
                    if abs(centre - sum((c.bbox.y0 + c.bbox.y1) / 2 for c in r) / len(r)) <= tol),
                   None)
        if row is None:
            out.append([char])
        else:
            row.append(char)
    for row in out:
        row.sort(key=lambda c: c.bbox.x0)
    return out


def _join(chars: list[Span]) -> Span:
    return Span(
        norm_ws("".join(c.text for c in chars)),
        BBox(min(c.bbox.x0 for c in chars), min(c.bbox.y0 for c in chars),
             max(c.bbox.x1 for c in chars), max(c.bbox.y1 for c in chars)),
        round(statistics.median(c.size for c in chars), 2),
        chars[0].font, chars[0].bold, chars[0].italic,
    )


def cells(row: Sequence[Span], em_: float) -> list[tuple[Span, ...]]:
    """Segment one baseline row into cells, each a tuple of words.

    Two thresholds on the same character stream: a space-sized gap ends a word,
    a gap over an em ends a cell. A single absolute threshold cannot do both,
    which is how a whole table row became one line.
    """
    word_gap, cell_gap = em_ * TUNING["word_gap_em"], em_ * TUNING["cell_gap_em"]
    out: list[tuple[Span, ...]] = []
    words: list[Span] = []
    chars: list[Span] = []
    for char in row:
        if chars:
            gap = char.bbox.x0 - chars[-1].bbox.x1
            if gap > cell_gap:
                words.append(_join(chars))
                out.append(tuple(words))
                words, chars = [], []
            elif gap > word_gap:
                words.append(_join(chars))
                chars = []
        chars.append(char)
    if chars:
        words.append(_join(chars))
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
- Produces: `bands(chars, width, em_) -> list[tuple[float, float]]` and
  `build(chars: Sequence[Span], width: float, height: float) -> tuple[TextBlock, ...]`.
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
        out += _chars(f"L{i}", 20.0, y=y) + _chars(f"R{i}", 240.0, y=y)
    return out


def test_bands_find_the_gutter_between_two_columns():
    found = bands(_two_columns(), PAGE_W, EM)
    assert len(found) == 2
    assert found[0][1] < 240.0 <= found[1][0]


def test_a_single_column_page_is_one_band():
    assert len(bands(_chars("ABC", 20.0), PAGE_W, EM)) == 1


def test_build_reads_the_left_column_before_the_right():
    text = " ".join(b.text for b in build(_two_columns(), PAGE_W, PAGE_H))
    assert text.index("L2") < text.index("R0"), text


def test_build_conserves_every_character():
    chars = _two_columns()
    produced = "".join(s.text for b in build(chars, PAGE_W, PAGE_H) for s in b.spans)
    assert sorted(produced.replace(" ", "")) == sorted("".join(c.text for c in chars))


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
def bands(chars: Sequence[Span], width: float, em_: float) -> list[tuple[float, float]]:
    """Column bands, found as maximal x-runs no character crosses.

    Deliberately geometric: the layout model misses 50-65% of spans on dense
    pages, so it can classify columns but must never define them.
    """
    covered = [False] * (int(width) + 1)
    for char in chars:
        for x in range(max(0, int(char.bbox.x0)), min(int(width), int(char.bbox.x1)) + 1):
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


def _band_of(char: Span, found: list[tuple[float, float]]) -> int:
    centre = (char.bbox.x0 + char.bbox.x1) / 2
    for i, (x0, x1) in enumerate(found):
        if x0 <= centre <= x1:
            return i
    return min(range(len(found)),
               key=lambda i: min(abs(centre - found[i][0]), abs(centre - found[i][1])))


def build(chars: Sequence[Span], width: float, height: float) -> tuple[TextBlock, ...]:
    """Characters with geometry into blocks: bands, then rows, then cells.

    Reading order is band order, then top to bottom. Nothing merges across a
    band, and no line merges across a cell boundary.
    """
    if not chars:
        return ()
    em_ = em(chars)
    found = bands(chars, width, em_)
    out: list[TextBlock] = []
    for index in range(len(found)):
        in_band = [c for c in chars if _band_of(c, found) == index]
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

### Task 6: Rewire the PDFium adapter onto `blocks.build()`

**Files:**
- Modify: `sidecar-v3/ingest/pdfium_extract.py`
- Modify: `sidecar-v3/tests/test_pdfium_extract.py`

**Interfaces:**
- Consumes: `ingest.blocks.build`.
- Produces: `_font(text_page, index) -> tuple[str, float, bool, bool]` and
  `_chars(text_page, height, font_of=_font) -> tuple[Span, ...]`, plus
  `extract(pdf_path, doc_id=None) -> RawExtraction` with real blocks. Task 8
  gates it.

The font lookup is injected rather than called inline so the geometry stays
testable against a fake text page, and so the character index used for the font
is the same index the geometry came from. The current adapter sets `font=""` and
leaves `bold`/`italic` False on every span; `layout.py` builds `FontStats` from
those fields to classify headings, so a candidate that drops them cannot reach
the reference on heading-bearing pages.

- [ ] **Step 1: Write the failing tests**

Replace the body of `sidecar-v3/tests/test_pdfium_extract.py` with:

```python
"""The PDFium adapter is thin: characters out of PDFium, aggregation in
ingest.blocks. These tests pin the seam, not the aggregation."""
from domain.models import BBox
from ingest.pdfium_extract import _chars

PAGE_HEIGHT = 100.0
NO_FONT = lambda text_page, index: ("", 0.0, False, False)  # noqa: E731


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


def test_chars_report_top_left_origin_boxes():
    """PDFium measures y up from the bottom; BBox and every consumer of it use
    PyMuPDF's y-down top-left origin, the layout raster included."""
    got = _chars(_text_page([(10, 80, 14, 90)], "T"), PAGE_HEIGHT, font_of=NO_FONT)
    assert got[0].bbox == BBox(10, 10, 14, 20)


def test_chars_are_one_span_per_character():
    """Aggregation belongs to ingest.blocks; the adapter must not pre-group."""
    got = _chars(_text_page([(10, 80, 14, 90), (15, 80, 19, 90)], "AB"),
                 PAGE_HEIGHT, font_of=NO_FONT)
    assert [span.text for span in got] == ["A", "B"]


def test_chars_drop_whitespace_and_degenerate_boxes():
    boxes = [(10, 80, 14, 90), (14, 80, 18, 90), (30, 80, 30, 90)]
    got = _chars(_text_page(boxes, "A C"), PAGE_HEIGHT, font_of=NO_FONT)
    assert [span.text for span in got] == ["A"]


def test_chars_preserve_ligature_codepoints():
    """A ligature is one rendered character with one box; dropping or splitting
    it silently corrupts words like 'find' and 'flail'."""
    got = _chars(_text_page([(10, 80, 18, 90)], "\ufb01"), PAGE_HEIGHT, font_of=NO_FONT)
    assert [span.text for span in got] == ["\ufb01"]


def test_chars_ask_for_the_font_of_the_character_they_kept():
    """Skipped whitespace must not shift the font index off its character."""
    asked = []
    boxes = [(10, 80, 14, 90), (14, 80, 18, 90), (20, 80, 24, 90)]

    def spy(text_page, index):
        asked.append(index)
        return ("Serif", 10.0, False, False)

    _chars(_text_page(boxes, "A B"), PAGE_HEIGHT, font_of=spy)
    assert asked == [0, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_extract.py -q`
Expected: FAIL — `TypeError: _chars() got an unexpected keyword argument 'font_of'`
(after Task 5 the module still has the old helpers).

- [ ] **Step 3: Rewrite the adapter**

In `sidecar-v3/ingest/pdfium_extract.py`, delete `_line_spans`, `_words`,
`_word`, and `_page_blocks` — `blocks.build()` replaces all four — and add:

```python
_ITALIC_FLAG = 1 << 6  # PDF font descriptor flag bit 7


def _font(text_page, index: int) -> tuple[str, float, bool, bool]:
    """(name, size, bold, italic) for one PDFium character index."""
    flags = ctypes.c_int()
    n = pdfium_raw.FPDFText_GetFontInfo(text_page.raw, index, None, 0,
                                        ctypes.byref(flags))
    name = ""
    if n > 0:
        buf = ctypes.create_string_buffer(n)
        pdfium_raw.FPDFText_GetFontInfo(text_page.raw, index, buf, n,
                                        ctypes.byref(flags))
        name = buf.raw[:n - 1].decode("utf-8", "replace")
    low = name.lower()
    return (
        name,
        float(pdfium_raw.FPDFText_GetFontSize(text_page.raw, index)),
        pdfium_raw.FPDFText_GetFontWeight(text_page.raw, index) >= 700 or "bold" in low,
        bool(flags.value & _ITALIC_FLAG) or "italic" in low or "oblique" in low,
    )


def _chars(text_page, height: float, font_of=_font) -> tuple[Span, ...]:
    """One Span per rendered character, in PyMuPDF's y-down top-left space.

    PDFium measures y up from the bottom of the page; BBox and every consumer
    of it — the layout raster included — measure it down from the top. The font
    lookup is injected so geometry stays testable without a PDFium handle.
    """
    out: list[Span] = []
    for i in range(text_page.count_chars()):
        char = text_page.get_text_range(i, 1)
        if not char or char.isspace():
            continue
        x0, y0, x1, y1 = text_page.get_charbox(i)
        if x1 <= x0 or y1 <= y0:
            continue
        name, size, bold, italic = font_of(text_page, i)
        out.append(Span(char, BBox(x0, height - y1, x1, height - y0),
                        round(size or (y1 - y0), 2), name, bold, italic))
    return tuple(out)
```

Change the page loop inside `extract` to:

```python
        width, height = page.get_size()
        text_page = page.get_textpage()
        blocks = build(_chars(text_page, height), width, height)
        spans = tuple(span for block in blocks for span in block.spans)
```

Update the imports: drop `statistics`, add `import ctypes`,
`import pypdfium2.raw as pdfium_raw`, and `from ingest.blocks import build`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_extract.py -q`
Expected: PASS — all five tests.

- [ ] **Step 5: Write the failing integration tests**

Font metadata and rasterization need a real PDFium handle, so these run against
the corpus and skip when it is absent. Append to the same test file:

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


def test_spans_carry_font_name_and_weight():
    """layout.py builds FontStats from these fields to classify headings; an
    adapter that leaves them empty cannot reach the reference."""
    import pypdfium2

    page = pypdfium2.PdfDocument(str(_corpus_pdf("osric_2e")))[155]
    spans = _chars(page.get_textpage(), page.get_size()[1])
    assert any(span.font for span in spans)
    assert any(span.bold for span in spans)
    assert all(span.size > 0 for span in spans)


def test_rasterize_returns_rgb_pixels():
    from ingest.pdfium_extract import rasterize

    raster = rasterize(str(_corpus_pdf("cairn_1e")), 9, dpi=150)
    assert raster.ndim == 3 and raster.shape[2] == 3
    assert raster.dtype.name == "uint8"
```

- [ ] **Step 6: Run them**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests/test_pdfium_extract.py -q`
Expected: PASS. If `test_spans_carry_font_name_and_weight` fails, `_font` is
returning empty names — check the `FPDFText_GetFontInfo` buffer length handling
before changing the assertion.

- [ ] **Step 7: Run the full suite**

Run: `uv run --frozen --project sidecar-v3 pytest sidecar-v3/tests evals/tests -q`
Expected: PASS — every test.

- [ ] **Step 8: Commit**

```bash
git add sidecar-v3/ingest/pdfium_extract.py sidecar-v3/tests/test_pdfium_extract.py
git commit -m "refactor(v3/ingest): PDFium adapter delegates aggregation to ingest.blocks, keeps font metadata"
```

---

### Task 7: Document metadata — title, TOC, printed page labels

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

### Task 8: Gate the candidate and record the verdict

**Files:**
- Modify: `docs/roadmap/2026-08-28-permissive-pdf-backend-plan.md`
- Create: `evals/baselines/` outputs (written by the runs)

**Interfaces:**
- Consumes: the adapter from Tasks 6 and 7.
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
  pipeline version, and reindexing all happen only after Task 8 returns a GO.
- **The v2 sidecar.** `pymupdf4llm` keeps `check-third-party.py --release` red
  regardless of this plan's outcome. Scope is v3 only, by decision.
- **The packaging gate.** Spec section 6's macOS/Windows release smoke path
  needs a real release build, so it is verified at P4 cutover, not here.
- **A line-based W1 contract.** If Task 8 fails with regressions concentrated on
  `two_column` pages, the block abstraction is wrong and that contingency opens
  as its own design with a retrieval regression pass — not as a patch here.

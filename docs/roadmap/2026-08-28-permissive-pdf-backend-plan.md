# Permissive PDF Backend Replacement Plan

**Date:** 2026-08-28 (revised 2026-08-29)

**Status:** closed — NO-GO, verdict in §9; v2 ingestion kept

**Decision:** Legend Lore will retain its proprietary application license and
replace the AGPL PyMuPDF/PyMuPDF4LLM runtime. It will not ship that dependency
unless the product later obtains an Artifex commercial license. A replacement
is acceptable only if it preserves the quality of the current v3 W1 extraction
pipeline on the real TTRPG corpus.

## 1. Why This Is A Dedicated Workstream

PyMuPDF/MuPDF is dual-licensed under AGPL and a commercial agreement. The
downloadable PyInstaller sidecar directly imports and bundles it, so local-only
operation avoids the AGPL's remote-network clause but not the normal object-code
conveying obligations. The current proprietary `LICENSE` is incompatible with
the AGPL route.

The extraction quality after W1 is the correct reference, not an excuse to keep
an incompatible dependency. W1 fixed the material document-quality failure:
native PDF text lines carry content; the layout model only classifies and orders
them. It eliminated cross-column merges, torn stat blocks, and blank pages.

Scope is v3 only. The v2 sidecar keeps `pymupdf4llm`, so
`scripts/check-third-party.py --release` stays red until v3 becomes the shipping
pipeline. That is an accepted consequence of the scope, not an oversight.

## 2. Quality Reference And Evidence So Far

The reference configuration is `v3 --pdf-backend pymupdf` with W1 native-block
handling. On the 40-page golden suite it has no per-page regressions against
v2:

| metric | PyMuPDF W1 reference |
|---|---:|
| content recall | 1.000 |
| reading order | 1.000 |
| table-cell integrity | 0.982 |
| per-page gate regressions | 0 |

Corpus-wide QA over 1,440 pages reports 0 empty pages, 1.000 block recall,
1.000 label integrity, and only 2 broken native blocks among 10,319 measured.

Two permissive experiments have been run. Neither is a replacement candidate:

| backend | content | order | table cells | gate regressions | verdict |
|---|---:|---:|---:|---:|---|
| PDFium via pypdfium2 (thin adapter) | 0.972 | 0.958 | 0.549 | 18 | superseded |
| **PDFium + `ingest/blocks.py`** | **0.994** | **0.978** | **0.982** | **3** | **near-miss, see §9** |
| pdfplumber/pdfminer + PDFium rendering | 0.951 | 0.811 | 0.914 | 10 | no-go |

The PDFium-only adapter required fragile character-to-word reconstruction.
pdfplumber improves word geometry but still does not supply the stable block
hierarchy needed for the OSRIC and SRD two-column layouts, as well as Cairn's
equipment tables.

### 2.1 What The Two NO-GOs Actually Established

Re-measured on 2026-08-29 against the frozen reference
`evals/baselines/2026-08-29-v3-w1-reference.json`, after two defects were fixed.

**The first PDFium record was an artifact.** `ingest/pdfium_extract.py` sorted
rows by y ascending, but PDFium's `get_charbox()` measures y *up* from the
bottom of the page while `BBox` and every consumer use PyMuPDF's y-down
top-left origin. Every page came out bottom-to-top. `reading_order` is
`1 - inversions / C(n,2)`, so a fully inverted page scores 0.0 and the recorded
0.204 was near-total inversion, not weak extraction. With the conversion applied
at the source, PDFium scores **0.958**.

**The reference itself was never frozen.** `evals/engines/v3.py` passed
`rasterizer=None` for the default backend, which overrides `layout()`'s
`rasterizer=rasterize` default instead of falling back to it, so every v3 run
raised `TypeError: 'NoneType' object is not callable`. The W1 numbers in section
2 therefore came from a pre-spike run that was never committed as a baseline.
Both defects are fixed and the reference is now on disk.

**The two candidates fail in opposite ways.** Per-kind, against that reference:

| kind | PDFium content / order / cells | pdfplumber content / order / cells |
|---|---|---|
| prose | 0.956 / 0.929 / — | 0.967 / 0.917 / — |
| table | 0.978 / — / **0.549** | 0.978 / — / **0.914** |
| two_column | **1.000 / 1.000** / — | **0.800 / 0.600** / — |

PDFium separates columns perfectly and destroys table cells: `_line_spans`
splits a row only on gaps wider than `max(18.0, median_char_width * 6)`, so an
entire table row merges into one line. On OSRIC p.40 the header row extracts as
`Level Climb Walls Find Traps Hear Noise Shadows Move Quietly Open Locks Pick
Pockets Lan` where PyMuPDF yields one line per cell. That is the synthetic row
across columns which section 3 requirement 4 forbids. Thirteen of PDFium's
eighteen regressions are `table_cells`.

pdfplumber holds cells together and mangles columns instead, splitting on a flat
18% of page width.

Neither weakness belongs to its engine. Each lives in that adapter's hand-rolled
aggregation, and each engine is strong exactly where the other is weak.

The framing correction follows. PDF has no block primitive. MuPDF synthesizes
blocks in `source/fitz/stext-device.c` - characters clustered into lines by
baseline continuity, lines into blocks by flow proximity. PyMuPDF is not
exposing structure the format contains, it is exposing *its aggregation
heuristic*, and that heuristic is what W1 depends on. "Find an engine with a
stable block hierarchy" is unsatisfiable. The aggregation is ours to own.

## 3. Non-Negotiable Requirements

Every candidate must meet all of these requirements before it reaches the
production sidecar:

1. The package, its native binary, and every shipped data/model asset have an
   approved permissive license under `third_party/POLICY.md`.
2. It works fully locally: no hosted extraction service, account, telemetry
   requirement, or query-time network request.
3. It provides or supports reconstruction of text with stable page geometry.
4. It preserves text order without forming synthetic rows across columns.
5. It can render PDF pages to RGB pixels for the local ONNX layout model.
6. It can support required PDF metadata or has an explicit replacement strategy
   for title, page count, outline/TOC, and printed page labels.
7. It passes the quality and performance gates in section 6.

The candidate may be slower at indexing than PyMuPDF only if it remains under
the product's 15-minute target for a representative 400-page book. Interactive
search latency is unaffected once indexing has completed.

## 4. Candidate Evaluation Process

Run candidates as isolated adapters behind the existing `RawExtraction` typed
interface. Do not replace the default backend or modify retrieval work to make a
candidate look better.

### 4.1 License And Packaging Review

For each candidate, add a `review_required` record to
`third_party/components.json` before adding it to a runtime dependency list.
The record must identify:

- Package and native-engine version.
- SPDX license for bindings and engine separately.
- Upstream source and release/revision.
- Distribution notices and bundled licenses.
- Model/data assets, if any, with license and checksum.
- macOS and Windows packaging support.

Move the record to `approved` only after the exact shipped version and notices
are verified. A candidate that is technically good but license-ambiguous is a
no-go.

### 4.2 Capability Spike

Build a small adapter under `sidecar-v3/ingest/` that produces:

```text
RawExtraction
  -> PageExtract
    -> TextBlock
      -> TextLine
        -> Span(text, bbox, font metadata)
```

The adapter must use a conservative invariant: it may split at an extraction
engine's existing word or line boundary, but it may never merge content from
opposite columns merely because it shares a vertical coordinate.

Use PDFium rendering through `pypdfium2` where the candidate does not offer an
approved renderer. Keep rasterization separate from text extraction so each
component can be replaced independently.

### 4.3 Focused Fixture Gate

Before running the full corpus, test the candidate against explicit fixtures:

- SRD 5.1 Goblin/Hobgoblin stat page: labels must not cross columns.
- SRD 5.1 spell-area page: two short headed columns stay ordered.
- SRD 5.2.1 glossary: within-column line order survives.
- OSRIC pp.156 and 163: dense two-column prose remains readable.
- Cairn pp.10-11: text in visually table-like pages is not dropped.
- Black Hack class/stats: title and label/value rows remain separate.

Every one of those pages already carries a golden spec, so the fixture set is
`evals/extraction/golden/phase0.yaml` ids g28 and g33 (SRD 5.1 pp.315, 103),
g09 and g10 (SRD 5.2.1 pp.91-92), g34 and g35 (OSRIC pp.156, 163), g39 and g40
(Cairn pp.10-11), and g06 and g08 (Black Hack pp.4, 6). Fixture work reuses
those phrase specs rather than inventing a parallel set.

The local side-by-side inspector is the manual check:

```bash
uv run --frozen --project sidecar-v3 python -m evals.extraction.review \
  --engine v3 --doc osric_2e --pages 156,163 --open
```

For a candidate backend, add its backend switch to this command and inspect the
same pages before treating aggregate scores as sufficient evidence.

## 5. Implementation Sequence

### P0: Freeze The Reference

1. Keep `pymupdf` as the default v3 extraction backend during the search.
2. Keep the current W1 golden and corpus-QA reports as the quality reference.
3. Retain `--pdf-backend pdfium` and `--pdf-backend pdfplumber` only as
   experimental evaluation paths; neither may feed retrieval baselines.
4. Maintain the release license gate, which intentionally blocks shipping while
   PyMuPDF remains bundled.
5. Freeze the W1 golden and corpus-QA reports as committed JSON artifacts before
   any dependency removal. The fixture probe and
   `evals/extraction/corpus_qa.py` both grade against PyMuPDF W1 output, so
   dropping the dependency without a frozen reference blinds the very gates that
   authorize the cutover.

### P1: Screen - Resolved 2026-08-29

The screen ran as a full-gate head-to-head rather than a fixture probe, because
fixing the two defects in section 2.1 required those runs anyway. It settled the
question it existed to settle:

- **PDFium is the word source.** C++-backed, already vendored, already
  allowlisted, and it separates columns perfectly (two_column 1.000 / 1.000).
- **pdfplumber is retained as the cell-segmentation reference.** Its
  `table_cells` 0.914 is the number PDFium has to reach.
- **pdfminer.six `LTTextBox` is not probed.** PDFium already answers the
  structural question, and pdfminer is pure Python with a live risk against the
  15-minute / 400-page gate. Revisit only if P2 stalls.

One primitive question moves into P2 rather than staying a separate phase:
whether PDFium page **text objects** (`FPDF_PAGEOBJ_TEXT` through
`PdfPage.get_objects()`) separate table cells for free, since a cell is usually
its own text-showing operator.

Before further work, close a standing section 4.1 gap: `pdfplumber` and its
`pdfminer.six` dependency were added to `sidecar-v3/pyproject.toml` by the first
spike without an inventory record. Add both to `third_party/components.json` as
`review_required` with their exact versions. The check script validates the
records that exist; it cannot see a shipped dependency that was never declared.

### P2: Own The Aggregation

The aggregation is ours to write, on PDFium word geometry. Section 2.1 shows
both candidate weaknesses live in hand-rolled aggregation rather than in either
engine, so this is a bounded algorithm rather than an open-ended search. Two
files, split so the algorithm never depends on a PDF library:

- `sidecar-v3/ingest/blocks.py` — `build(spans, width, height) -> tuple[TextBlock, ...]`,
  importing no PDF library. It is unit-testable on synthetic geometry, and the
  word source stays swappable without touching it.
- `sidecar-v3/ingest/<winner>_extract.py`, named for the engine P1 selects —
  thin: open the PDF with that engine, produce `Span`s, call `blocks.build()`,
  and assemble `PageExtract` and `RawExtraction`.

The algorithm runs in three stages:

1. **Column bands.** Vertical whitespace projection over word boxes; a gutter is
   a maximal zero-coverage x-range spanning most of the page height. One band
   when no gutter is found.
2. **Lines within a band.** Baseline clustering on a tolerance derived from
   median glyph height, ordered left to right.
3. **Cells within a line.** Split a row wherever the horizontal gap exceeds the
   page's own inter-word gap distribution, rather than a fixed point threshold.
   This is the defect that costs PDFium 13 of its 18 regressions: a constant
   `max(18.0, median_char_width * 6)` merges an entire table row into one line.
   Evaluate PDFium text objects here first - if a cell is its own text-showing
   operator, the boundary is given rather than inferred.
4. **Blocks within a band.** Split the line sequence on a vertical gap greater
   than k times median line spacing, a dominant font-size change, or an indent
   change.

Reading order is band order, then top to bottom. Nothing merges across bands,
and no line merges across a cell boundary.

Implementation requirements:

1. Leave `ingest/extract.py` unchanged until the candidate passes its gate.
2. Make the section 4.2 conservative invariant two property tests rather than a
   comment, run over every fixture page: **conservation**, every input span
   appears in exactly one output block; and **no-straddle**, no block's spans
   cross a band boundary.
3. Add unit tests for whitespace, ligatures, words, line reconstruction,
   two-column separation, font metadata, page dimensions, and rendering.
4. Extend `V3Engine` and `evals.run_eval` with an explicit candidate backend
   selector used only by the extraction suites.
5. Preserve the existing W1 layout contract: layout labels may classify text but
   must not own, merge, or discard text-bearing units.
6. Supply title, page count, TOC, and printed page labels with parity tests, or
   document a named replacement reader per field. This is a tracked gap, not a
   footnote: both dead adapters returned an empty `toc` and empty `page_labels`,
   and the v3 storage schema persists both. pdfminer exposes outlines and
   pypdfium2 has `get_toc()`; printed page labels are the hard field and may
   need a small standalone reader over the PDF `/PageLabels` number tree.

**Anti-overfitting rule.** This is P2's real failure mode. Tunable constants live
in a single dict at the top of `blocks.py` and may be tuned *only* against the
ten section 4.3 fixture pages. The 40-page golden set is the gate: run after
tuning, never during. A failing golden page earns a structural change to the
algorithm, or becomes a new fixture by deliberate commit per section 7, never a
constant nudged until that page goes green.

### P3: Evaluate And Decide

1. Run the 40-page extraction gate against the v2 reference baseline.
2. Run the same gate against the current PyMuPDF W1 baseline.
3. Run corpus-wide extraction QA with no writes.
4. Generate side-by-side reports for all pages reported as broken, missing, or
   empty, plus the focused fixtures.
5. Measure wall time for extraction and rasterization on the 400-page corpus
   representative.
6. Verify title, page count, TOC, and printed page-label parity against the
   frozen reference.
7. Record the exact results and a Go/No-Go verdict in this document or a linked
   findings note.

### P4: Adopt Only After Parity

1. Make the approved backend the v3 default.
2. Remove PyMuPDF imports from v3 ingestion, evaluation oracle tooling, and
   packaged v3 dependencies.
3. Keep the old implementation only long enough to reproduce the reference;
   remove it before a release rather than maintaining two production extractors.
4. Bump the pipeline version and require a full v3 reindex.
5. Re-run extraction, retrieval, blind readability, and local-agent evaluations
   on a fresh index before declaring the cutover ready.
6. Update the component inventory to `approved`, include required notices, and
   verify the release license gate passes.

## 6. Go/No-Go Gates

A candidate is a **GO** only if all requirements hold:

| gate | required result |
|---|---|
| licensing | approved permissive license and complete notices |
| golden content | every page at least the v2 reference score |
| golden order | every scored page at least the v2 reference score |
| golden tables | every scored page at least the v2 reference score |
| corpus pages | no empty pages created by extraction |
| corpus integrity | block recall and label integrity at least the W1 reference |
| manual review | no column merge, torn stat line, or table corruption on focused fixtures |
| metadata | title, page count, TOC, and printed page labels match the frozen reference, or each gap has a named replacement reader |
| performance | representative 400-page indexing within 15 minutes |
| packaging | local macOS/Windows release smoke path works without network access |

Any gate failure is a **NO-GO**. Record the failure, remove the candidate from
the short list, and do not tune ranking or alter the eval specification to hide
it.

## 7. Risks And Fallbacks

| risk | response |
|---|---|
| No permissive engine reaches W1 extraction quality | obtain an Artifex commercial license or reconsider open-sourcing under AGPL; do not ship a lower-quality backend |
| A candidate has good text but no stable blocks | reject it unless a bounded, fixture-proven geometry adapter closes the gap |
| Layout classification drops candidate text | preserve text-bearing units as prose; classification is advisory, not permission to discard content |
| PDF metadata is incomplete | use a separate approved metadata reader only if it preserves the single typed raw-extraction contract |
| Candidate passes golden pages but fails corpus QA | no-go; expand the golden fixture set with the discovered page before evaluating another candidate |
| The block builder passes its property tests but the golden gate still regresses | read the cluster: regressions concentrated on `two_column` pages mean the block abstraction itself is wrong, so open a line-based W1 contract as its own design with a retrieval regression pass; regressions scattered across `table` pages are Stage C linearization work, not Stage A |
| Removing PyMuPDF deletes the oracle the gates depend on | freeze the W1 golden and corpus-QA outputs as committed artifacts before the dependency is dropped (P0.5) |
| A permissive adapter has good text but no document metadata | supply title, TOC, and page labels from the same engine where possible, or a named standalone reader per field; empty `toc`/`page_labels` is a gate failure, not an acceptable default |

## 9. Verdict — 2026-08-29

**NO-GO by the letter of section 6**, on three per-page regressions. The
candidate is far closer than any previous one, and the failures are specific
rather than systemic.

### What was built

PDFium supplies one `Span` per page text object; `sidecar-v3/ingest/blocks.py`
owns all aggregation — runs into words and cells, cells into rows, rows into
column-bounded blocks. PyMuPDF is no longer imported by any aggregation or
candidate-backend module (`ingest/raw.py` holds the shared types).

### Measured results

| gate row | result | reference | verdict |
|---|---|---|---|
| licensing | pypdfium2 BSD-3-Clause / Apache-2.0, inventory complete | allowlisted | **PASS** |
| golden content | 0.994 | 1.000 | **FAIL** — g02 1.000 → 0.750 |
| golden order | 0.978 | 1.000 | **FAIL** — g17 1.000 → 0.833, g35 1.000 → 0.905 |
| golden tables | 0.982 | 0.982 | **PASS** — no per-page table_cells regression |
| corpus pages | 0 empty of 1,440 | 0 | **PASS** |
| corpus integrity | block recall 0.998, label integrity 0.997 | 1.000 / 1.000 | **FAIL** — marginal |
| metadata | exact TOC and page-label parity | parity | **PASS** |
| performance | 208 pages in 3.55s; a 400-page book ≈ 7s | under 15 min | **PASS** |
| manual review | not performed — the side-by-side inspector needs a browser | no corruption | **NOT DONE** |
| packaging | deferred to P4 cutover | smoke path works | **DEFERRED** |

### The three surviving regressions

Independent of one another — different documents, layout regimes, and metrics:

- **g02** `osric_2e` p.40, content_recall 0.750. The thief-skills table, whose
  source kerning splits words mid-glyph.
- **g17** `black_hack_1e` p.3, reading_order 0.833. A plain prose page.
- **g35** `osric_2e` p.163, reading_order 0.905. A numbered room list interleaved
  with prose.

None share a cause, so no single further fix closes the gate.

### The finding that deserves the most weight

Corpus-wide `block_integrity` is **0.660** — 3,506 of 10,319 blocks are
segmented differently from PyMuPDF — and `adjacency` is 0.885, meaning about
11% of neighbouring block pairs are ordered differently. Some of that is by
construction: this design deliberately emits table rows as blocks and groups
prose into paragraphs, which is not how MuPDF segments. But a third of blocks
differing is a real structural difference, it is invisible to the extraction
gate, and chunking and retrieval consume exactly this structure. Any decision to
adopt should measure retrieval, not just extraction.

### Residual risk not measured by the gate: `Span.size` is ink height, not declared type size

`pdfium_extract._span` sets `Span.size` from the text object's own bounding
box (`bbox.y1 - bbox.y0` — glyph ink height); PyMuPDF sets it from the PDF's
declared font size. The two correlate but are not the same quantity: ink
height is roughly 0.7x declared size, and — unlike declared size, which takes
one of a handful of values per document — it varies continuously per run,
since kerning, ascenders/descenders, and per-glyph rendering all move the ink
bbox a little.

Measured: `black_hack_1e` p.4 yields 18 distinct block sizes under PDFium
versus 3 under PyMuPDF; `osric_2e` p.40 gives 13 versus 4.

This matters because `sidecar-v3/ingest/structure.py`'s `build_sections`
takes `body_size` as the mode of prose sizes and derives heading levels from
the sorted set of distinct heading sizes (`_HEADING_FONT_RATIO = 1.15`).
Continuous ink-heights push every heading toward its own distinct level, and
turn the `>= body * 1.15` comparison into noise rather than a clean signal —
because two runs set at the same declared type size can still land on either
side of that ratio purely from ink-height jitter. Retrieval consumes sections
as chunk parents, so a degraded section tree degrades retrieval quality one
step downstream of anything the extraction gate checks.

**No gate row measures this.** The extraction gate scores content, reading
order, and table cells — never section-tree shape — so this risk is currently
invisible to every number in the table above.

To be clear about what this is *not*: the underlying text content is
demonstrably correct (content_recall 0.994, table_cells 0.982). This is a
risk to the section tree PDFium-backed documents would build downstream, not
to extraction itself, and it is unmeasured rather than confirmed to cause a
retrieval regression.

Corollary: `blocks.em()` is the median run's ink height, roughly 0.7x the
declared type size, so every `TUNING` constant in `sidecar-v3/ingest/blocks.py`
is about 1.4x tighter in practice than the module's former docstring wording
("multiples of the row's em, its type size") implied. That wording has been
corrected in-code to describe what is actually measured.

### Paragraph under-splitting, measured

`blocks.py` splits a paragraph when the whitespace between two rows exceeds
`block_gap_lines` (1.60) times the median centre-to-centre pitch. Those two
quantities are not dimensionally comparable, so the effective bar is several
normal line gaps.

Measured against PyMuPDF's paragraph blocks over four prose pages
(black_hack_1e p.3, osric_2e p.135, srd_5_2_1 p.92, bfrpg_4e p.176), as a
fraction of pitch:

| | p50 | p90 | max |
|---|---:|---:|---:|
| whitespace within a paragraph | -0.021 | 0.320 | 0.526 |
| whitespace at a real break | 0.488 | 1.630 | 11.344 |

Within-paragraph whitespace is frequently negative — ascenders and descenders
overlap — which is why it is a poor quantity to threshold. The current setting
catches roughly 10% of true paragraph breaks and produces no false splits.

Comparing pitch to pitch is dimensionally sound but no better: the
distributions still overlap (within p90 1.559 against break p50 1.175) and the
best separator catches about 72% of breaks at the cost of about 19% false
splits.

**The threshold was re-derived on 2026-08-30 and lowered to 0.90.** The four
pages above include black_hack_1e p.3, which is golden page g17, so that sample
could not be used to set a constant without tuning against the gate. The sweep
was redone over 26 pages sampled across all seven corpus documents and chosen
disjoint from the 40-page golden set (1,485 gaps):

| threshold | false splits | breaks caught |
|---:|---:|---:|
| 1.60 (previous) | 0.0% | 7.4% |
| **0.90 (current)** | **0.0%** | **11.9%** |
| 0.70 | 0.8% | 15.9% |
| 0.60 | 1.5% | 22.4% |
| 0.40 | 3.2% | 40.4% |

On this larger sample within-paragraph whitespace reaches 0.770 pitch, not the
0.526 the four-page sample suggested — so values in (0.53, 0.70] are not in fact
free. 0.90 is the largest setting that still splits nothing it should not, and it
strictly dominates 1.60: identical zero false splits, 60% more breaks found. The
40-page gate is unchanged by the switch (0.994 / 0.978 / 0.982, the same three
regressions), confirming it neither helps nor harms the measured axes.

Going below 0.90 buys recall at the cost of real false splits, and there is no
evidence yet on which of over- and under-splitting hurts retrieval more. That is
a retrieval question, not an extraction one.

The consequence is real and unmeasured by the extraction gate: paragraphs that
should be separate blocks are merged, which contributes to the corpus
`block_integrity` of 0.660 alongside the defects fixed after the final review.

Corpus QA was re-run after the fix wave (2026-08-30) and 0.660 is **unchanged** —
block recall 0.998, label integrity 0.997, adjacency 0.885, 0 empty pages, with
only trivial per-document movement (osric 1489 → 1487 broken, srd_5_1 706 → 707)
netting to the same 3,506. The gutter fix moved blocks in both directions and the
effects cancelled: it stops folding a running header into a column, but a
multi-line full-width element on a two-column page now fragments into one block
per line where it was previously one wrongly merged block.

The divergence is therefore real and not an artifact of any defect since fixed.
Retrieval consumes these blocks as chunks, so this belongs in any adoption
decision.

### What was corrected along the way

Two defects invalidated the earlier evidence and are fixed:

1. The recorded PDFium `reading_order` 0.204 was a y-axis convention bug in the
   adapter, not an engine limit. PDFium measures y up from the page bottom;
   `BBox` measures it down from the top. Corrected, the same code scores 0.958.
2. `evals/engines/v3.py` passed `rasterizer=None` for the default backend,
   overriding `layout()`'s default, so **every** v3 evaluation run raised
   `TypeError` from commit b7c295d onward. The W1 reference in section 2 had
   therefore never been committed; it is now frozen at
   `evals/baselines/2026-08-29-v3-w1-reference.json`.

## 8. Definition Of Done

The backend replacement is complete only when Legend Lore can package and ship
the v3 pipeline without PyMuPDF or PyMuPDF4LLM, passes every gate above, and
retains the current W1 extraction quality on the real corpus. Until then,
PyMuPDF remains a development-only quality reference and the release license
gate stays blocked.

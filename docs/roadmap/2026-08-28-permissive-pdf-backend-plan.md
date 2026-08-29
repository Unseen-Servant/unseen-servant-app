# Permissive PDF Backend Replacement Plan

**Date:** 2026-08-28

**Status:** active research and implementation plan

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
| PDFium via pypdfium2 | 0.981 | 0.204 | 0.604 | 23 | no-go |
| pdfplumber/pdfminer + PDFium rendering | 0.951 | 0.811 | 0.914 | 10 | no-go |

The PDFium-only adapter required fragile character-to-word reconstruction.
pdfplumber improves word geometry but still does not supply the stable block
hierarchy needed for the OSRIC and SRD two-column layouts, as well as Cairn's
equipment tables.

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

### P1: Select A Better Structural Candidate

1. Identify engines that expose genuine word/line/block primitives, not only a
   character stream or pre-flattened page text.
2. Eliminate candidates that fail the license review before adapter work.
3. Run a one-page geometry spike on the fixtures in section 4.3.
4. Choose at most one candidate for a full adapter. Do not accumulate partially
   maintained extraction paths.

### P2: Implement The Adapter

1. Add the adapter under `sidecar-v3/ingest/` and leave
   `ingest/extract.py` unchanged until it passes its gate.
2. Add unit tests for whitespace, ligatures, words, line reconstruction,
   two-column separation, font metadata, page dimensions, and rendering.
3. Extend `V3Engine` and `evals.run_eval` with an explicit candidate backend
   selector used only by the extraction suites.
4. Preserve the existing W1 layout contract: layout labels may classify text but
   must not own, merge, or discard text-bearing units.
5. Add title, TOC, and printed-label parity tests, or document which fields need
   a separate metadata reader.

### P3: Evaluate And Decide

1. Run the 40-page extraction gate against the v2 reference baseline.
2. Run the same gate against the current PyMuPDF W1 baseline.
3. Run corpus-wide extraction QA with no writes.
4. Generate side-by-side reports for all pages reported as broken, missing, or
   empty, plus the focused fixtures.
5. Measure wall time for extraction and rasterization on the 400-page corpus
   representative.
6. Record the exact results and a Go/No-Go verdict in this document or a linked
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

## 8. Definition Of Done

The backend replacement is complete only when Legend Lore can package and ship
the v3 pipeline without PyMuPDF or PyMuPDF4LLM, passes every gate above, and
retains the current W1 extraction quality on the real corpus. Until then,
PyMuPDF remains a development-only quality reference and the release license
gate stays blocked.

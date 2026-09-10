# evals — the v3 retrieval harness

Engine-agnostic evaluation for the retrieval pipeline. It grades the **live v2
sidecar today** (via an in-process TestClient) and will grade **sidecar-v3** as
it is built — same queries, same grader, so every Phase-1+ change is measured
against a committed baseline it must beat. See
[docs/retrieval/2026-08-14-v3-scaffold.md](../docs/retrieval/2026-08-14-v3-scaffold.md)
and [docs/roadmap/2026-08-13-pipeline-rebuild-plan.md](../docs/roadmap/2026-08-13-pipeline-rebuild-plan.md).

Grading is **deterministic anchor-match, no LLM judge**: a chunk is relevant iff
hand-authored anchors appear in its text (plus a scope-dependent doc-match). The
old ground truth was once 30% wrong, so nothing is trusted on faith — every
anchor is re-verified against both the reference and the PDF, and a blind manual
round measures whether the automated grade tracks a human's.

## Corpus (the gate)

The corpus is a **parallel corpus**: each system is one PDF paired with a
digital-native reference (SRD Markdown, OSRIC/Black Hack/YZE HTML, Cairn
Markdown, BFRPG ODT). The reference is the machine-checkable ground truth.

- `evals/corpus/` holds it and is **gitignored** (113 MB, openly licensed but not
  git's job). `corpus.manifest.json` lives *beside* it and **is committed** — it
  pins every PDF by SHA-256 and every reference tree by an aggregate digest.
- `corpus.py` resolves the corpus in order: `$LL_EVAL_CORPUS` → `evals/corpus/`
  in the current tree → the main checkout's copy (so worktree runs work).
- **The harness refuses to run on any hash/digest drift.** That refusal is the
  guard against the silent ground-truth drift that produced the old 30%-wrong GT.

## Run it

All commands from the repo root, under the sidecar env. Retrieval needs Ollama
up (query embedding); extraction does not.

```bash
# Retrieval — scope-aware, MRR@5 headline. Each normal run builds a fresh,
# temporary index, so a baseline cannot use stale chunks from an earlier
# pipeline version. Writes evals/baselines/<date>-v2-phase0.*
uv run --project sidecar python -m evals.run_eval --engine v2 --baseline phase0

# A candidate retrieval rung must not regress headline metrics in any scope.
uv run --project sidecar-v3 python -m evals.run_eval --engine v3 --baseline rung-9 \
    --gate evals/baselines/<last-committed>-v3-<rung>.json

# Extraction QA — no Ollama; grades hand-authored golden pages. --gate fails
# the run (exit 1) if ANY page's metric drops below the reference baseline —
# the per-page min, not the mean, is what gates an extraction change.
uv run --project sidecar python -m evals.run_eval --engine v2 --suite extraction
uv run --project sidecar-v3 python -m evals.run_eval --engine v3 --suite extraction \
    --gate evals/baselines/<last-committed>-v3-extraction.json

# Author-time guard: every anchor present in BOTH reference and PDF (gates a
# query commit; also confirms cross_page anchors straddle their declared pages).
uv run --project sidecar python -m evals.retrieval.verify_anchors

# Corpus-wide extraction QA — every page with native text blocks, the PDF as
# the oracle, no embedding
# (~7 min). The inner loop for extraction work; v3 runs under its own env.
uv run --project sidecar-v3 python -m evals.run_eval --engine v3 --suite corpus-qa

# Local visual review: original rendered page, v3 extraction, and native-text
# oracle side by side. Start with the former trouble pages.
uv run --project sidecar-v3 python -m evals.extraction.review \
    --engine v3 --doc srd_5_2_1 --pages 30,183 --open

# Breadcrumb QA — every chunk's section_heading graded for markup, split
# letters, small-caps damage, furniture roots (no Ollama, ~8 min). The gate
# Phase 1's heading work must clear. Writes evals/baselines/<date>-v2-breadcrumb-qa.*
# The .md lists the residue — the most frequent flawed headings per book — so
# a fix can see what it did not catch.
uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa

# A candidate heading change must not raise any per-doc flaw rate.
uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa \
    --gate evals/baselines/<last-committed>-v2-breadcrumb-qa.json

# Harness unit tests (pure, CI-safe).
uv run --project sidecar-v3 pytest evals/tests
```

## What gates what

| gate | enforced by | blocks |
|---|---|---|
| corpus PDF hash + path-sensitive reference digest | `corpus.py` (`require_corpus`) | any eval run, on drift |
| every anchor in ref ∧ PDF | `retrieval/verify_anchors.py` (exit 1) | committing a query |
| the committed baseline (MRR@5, success@3) | `--gate` | a v3 rung that regresses in any scope |
| every golden page ≥ its reference score | `extraction/gate.py` (`--gate`, exit 1) | an extraction change that helps the mean and hurts a page |
| anchor grade vs a human (Cohen's κ) | `blind/score.py` | trusting the automated number |
| chunks a human can read (`readable@5`) | `blind/score.py` (the "garbled" tick) | calling a pipeline search-ready on anchors alone |
| no per-doc breadcrumb flaw-rate rise | `breadcrumb_qa.regressions` (`--gate`, exit 1) | a heading change that helps the mean and hurts a book |

## Suites

**Retrieval** (`retrieval/`) — `queries.yaml` is scope-aware; each query's `scope`
drives both how it's searched and how it's graded (the dial is the doc-match
requirement):

| scope | search | relevant iff | models |
|---|---|---|---|
| `single` | filtered to the file | anchors match | GM has a book open (common path) |
| `cued` | unfiltered, query names the system | anchors match **and** right file | the disambiguation target |
| `uncued` | unfiltered, no system named | anchors match, **any** file | ambiguous search |

Metrics (`metrics.py`): **MRR@5** (headline, known-item), nDCG@10, recall@3/@5/@10,
payload_chars (the small-model budget), dup_sections@10, latency p50/p95 —
macro-averaged by scope, category, and style.

**Extraction** (`extraction/`) — did the extractor get the right text, in the
right order, with intact table cells? `Engine.extract()` returns typed pages;
`grade.py` scores content_recall, reading_order (sentence-pair inversions), and
table_cells (contiguity) on hand-authored `golden/*.yaml` pages, over a ±1-page
window so segmenter page-attribution drift doesn't confound the score.
`verify_golden.py` re-verifies each golden fact in ref ∧ PDF, same as anchors.

**Corpus QA** (`extraction/corpus_qa.py`) — the golden suite is 30 pages
reported as a mean, which is how a column-interleaving layout defect on ~27 %
of pages shipped three times as a GO (recovery strategy §1.4). This axis
needs no spec: PyMuPDF's native text blocks are column-correct, so for every
page it counts native blocks (≥ 120 chars) that survive the engine's page text
**intact** (contiguous), **broken** (lines present, not contiguous — the
interleave signature) or **missing** (dropped; running headers are dropped on
purpose, so that is recall, not integrity), stat-block/spell **label lines**
("Armor Class 15 …") that survive whole, and **adjacency** — stacked
neighbouring blocks that are still consecutive (catches a stat line that
survives intact but lands under another creature). Reports `block_integrity`,
`block_recall`, `label_integrity`, `adjacency` per doc and the 20 worst pages.
Gate on the worst pages, not the mean.

**Library tier** (`retrieval/library.yaml`, `evals/library.py`) — graded queries
against YOUR indexed library, the confusable regime the 7-book corpus cannot
create. Books are pinned by the sidecar's own `content_hash`; the harness reads
the app's index (quit the app first), never indexes, and skips queries whose
book is absent. Local-only by construction: the YAML commits hashes + anchors,
never a PDF. `--suite library --data-dir <app data dir>`; verify with
`verify_anchors --library <app data dir>`.

## Baselines & the blind round

`baselines/<date>-<engine>-<rung>.{json,md}` are committed — the numbers to beat.
The v2 reference for the 2026-09-02 roadmap is `2026-09-02-v2-phase0b` (tags + twin rule +
budget column); gate against it, not `2026-08-15-v2-phase0`.
Every baseline records the corpus fingerprint, Git revision, and explicit query
knobs. Retrieval baselines always use a fresh temporary index; exploratory
reuse requires `--reuse-index --data-dir <path> --no-write` and cannot write a
baseline.
The retrieved chunks live in a gitignored `<stem>.results.json` (regenerable),
which drives two viewers:

```bash
# Self-contained HTML inspector: aggregates + per-query drill-in, scope filter.
uv run --project sidecar python -m evals.retrieval.report evals/baselines/<stem>

# Blind manual round — the trust check. Score the shuffled, hint-stripped
# scoresheet (tick "relevant" on answers, "garbled" on unreadable chunks),
# Export, then compare to the anchor grade (per-chunk agreement + Cohen's κ +
# readable@5 + the anchors to fix).
uv run --project sidecar python -m evals.blind.generate evals/baselines/<stem> --open
uv run --project sidecar python -m evals.blind.score    evals/baselines/<stem>
```

## Engines

`engines/base.py` is the `Engine` protocol (index / warmup / search / extract /
close). `engines/v2.py` drives the live sidecar in-process (its real pipeline).
`engines/v3.py` is a stub until sidecar-v3 has a pipeline (Phase 2).

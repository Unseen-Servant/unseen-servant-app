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
# Retrieval — scope-aware, MRR@5 headline. Indexing is idempotent (skips books
# already in evals/.eval_data/). Writes evals/baselines/<date>-v2-phase0.*
uv run --project sidecar python -m evals.run_eval --engine v2 --baseline phase0

# Extraction QA — no Ollama; grades hand-authored golden pages.
uv run --project sidecar python -m evals.run_eval --engine v2 --suite extraction

# Author-time guard: every anchor present in BOTH reference and PDF (gates a
# query commit; also confirms cross_page anchors really straddle a page break).
uv run --project sidecar python -m evals.retrieval.verify_anchors
```

## What gates what

| gate | enforced by | blocks |
|---|---|---|
| corpus PDF hash + reference digest | `corpus.py` (`require_corpus`) | any eval run, on drift |
| every anchor in ref ∧ PDF | `retrieval/verify_anchors.py` (exit 1) | committing a query |
| the committed baseline (MRR@5 etc.) | `evals/baselines/*.json` | a v3 rung that doesn't beat it |
| anchor grade vs a human (Cohen's κ) | `blind/score.py` | trusting the automated number |

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

## Baselines & the blind round

`baselines/<date>-<engine>-<rung>.{json,md}` are committed — the numbers to beat.
The retrieved chunks live in a gitignored `<stem>.results.json` (regenerable),
which drives two viewers:

```bash
# Self-contained HTML inspector: aggregates + per-query drill-in, scope filter.
uv run --project sidecar python -m evals.retrieval.report evals/baselines/<stem>

# Blind manual round — the trust check. Score the shuffled, hint-stripped
# scoresheet, Export, then compare to the anchor grade (per-chunk agreement +
# Cohen's κ + the anchors to fix).
uv run --project sidecar python -m evals.blind.generate evals/baselines/<stem> --open
uv run --project sidecar python -m evals.blind.score    evals/baselines/<stem>
```

## Engines

`engines/base.py` is the `Engine` protocol (index / warmup / search / extract /
close). `engines/v2.py` drives the live sidecar in-process (its real pipeline).
`engines/v3.py` is a stub until sidecar-v3 has a pipeline (Phase 2).

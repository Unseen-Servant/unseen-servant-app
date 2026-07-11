# Retrieval eval harness

Measures production search quality against a fixed ground truth, per the
[2026-07-09 search-quality goal](../../docs/roadmap/2026-07-09-search-quality-goal.md)
(Phase 2). Ported from `unseen-legend-lore-experiments/hybrid_retrieval_spike`
(`queries.yaml` + `score_retrieval.py`), regraded from page overlap to the
specific answer chunk.

## Run it

```bash
cd sidecar
uv run python -m evals.run_eval                          # print metrics
uv run python -m evals.run_eval --write-baseline NAME    # also write baselines/NAME.{json,md}
uv run python -m evals.run_eval --hybrid                 # BM25+RRF ablation (experimental search flag)
```

Prerequisites:

- **Ollama** running locally with `bge-m3` (same as production indexing).
- **The eval corpus** — three CC-licensed rulebooks, not committed to this
  repo. Default location is
  `~/code/unseen-legend-lore-experiments/chunker_spike/corpus`; override
  with `--corpus DIR`. Expected files:
  - `Basic-Fantasy-RPG-Rules-r142.pdf`
  - `Black-Flag-Roleplaying.pdf`
  - `SRD_CC_v5.1.pdf`

The first run indexes the corpus with the production pipeline (extraction →
chunking → bge-m3 embeddings) into `evals/.eval_data/` (gitignored, a few
minutes). Reruns reuse the index and only run the queries. Delete
`.eval_data/` to force a re-index after changing the indexing pipeline —
index-time changes don't show up in the metrics until you do.

## What it measures

40 pre-registered queries (30 locked from `chunker_spike`, 10 cross-system
from `hybrid_retrieval_spike`) run through the production `/api/search`
endpoint (rerank on unless `--no-rerank`; `--hybrid` turns on the
experimental BM25+RRF candidate fusion — see `lexical.py`). Reported per category —
`stat_block`, `table`, `prose`, `cross_page`, `cross_system` — and overall:

**The harness mimics the application experience**: requests send
`n_results=25` by default — the UI's first page (`PAGE_SIZE_INITIAL` in
`src/routes/+page.svelte`, pinned by `tests/test_eval_config.py`) — while
metrics stay graded on the top 10. Search behavior can depend on the
requested page size (the rerank candidate pool may scale with it), so
gating at a size the app never sends validates the wrong config: the
2026-07-10 #340 restructure passed at `n_results=10` and regressed the UI
at 25. Use `--page-size` for ablations at other sizes (e.g. 15, the MCP
default). Baselines record `page_size` in their meta; baselines written
before 2026-07-10 predate the flag and were measured at 10 — compare
like with like.

- **nDCG@10** — binary gains, normalized by the ideal ordering of the
  retrieved relevant results; 0 when nothing relevant is retrieved.
- **MRR@5** — reciprocal rank of the first relevant result in the top 5.
- **precision@5 / precision@10** — fraction of the top k that is relevant
  (missing results count as misses).
- **recall@5 / recall@10** — hit rate: did *any* relevant result appear in
  the top k. The full set of relevant chunks per query is unknown, so
  set-recall is not computable; this matches the spike's recall definition.
- **search latency** — per-query `/api/search` wall clock (mean / median /
  p95, nearest-rank), printed after the metrics table and stored per query
  and in baseline meta. Measured in-process through TestClient after one
  untimed warmup query (which absorbs the lazy cross-encoder / Ollama
  loads), so it captures embed + retrieval + rerank but not the HTTP
  transport the Tauri app or MCP client adds — compare configurations with
  it, don't quote it as end-to-end user latency.

**Relevance judgment** (the Phase 2 change): a result counts only if it
(a) comes from the expected source PDF, (b) overlaps a declared
ground-truth page range, and (c) its section-heading breadcrumb plus
chunk text contains all of the query's answer anchors — short phrases
from the answer text itself, matched after normalization (lowercase,
punctuation/layout collapsed). Page overlap
alone saturates: a wrong chunk from the right page counted as a hit.

## Files

- `queries.yaml` — ground truth: query text, source, page ranges
  (`lo-hi|lo-hi` alternatives), category, answer anchors.
- `scorer.py` — relevance judgment + metrics (unit-tested in
  `tests/test_eval_scorer.py`, CI-safe).
- `run_eval.py` — indexes the corpus once, runs the queries, prints the
  per-category table.
- `baselines/` — committed eval results for comparison over time.

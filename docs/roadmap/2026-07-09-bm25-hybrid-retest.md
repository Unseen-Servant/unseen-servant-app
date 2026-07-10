# BM25 / lexical hybrid re-test — NO-GO for default-on (flag retained)

**Date:** 2026-07-09
**Context:** The [2026-07-01 roadmap](2026-07-01-retrieval-pipeline-improvement-roadmap.md)
reopened the BM25 hybrid question: the prior spike NO-GO was narrow — untuned
uniform RRF over plain (non-heading) BM25, a 3-PDF English corpus, and a
page-overlap metric that saturates and could not see exact-chunk precision.
This re-test fixes the two of those objections the production repo can fix
today: it runs against the **production retrieval path** and grades on the
**answer chunk** (nDCG@10 / MRR@5 / precision@k / recall@k, per category)
via the [eval harness](../../sidecar/evals/README.md), and the BM25 index is
**heading-prepended** (the built-but-never-fused "V4" configuration), so the
lexical side sees the same text view as the embedder and reranker.

## What was built

- [sidecar/lexical.py](../../sidecar/lexical.py) — in-memory BM25 over all
  indexed chunks via stdlib sqlite FTS5 (`porter unicode61` tokenizer), plus
  reciprocal-rank fusion (k=60, untuned 1:1) and a mirror of the dense
  query's `where` scope for the lexical side. No new dependencies.
- A default-off `hybrid` flag on `/api/search`: BM25 top-(10×n) is fused
  with the dense top-(10×n) candidate ranking by RRF, then the unchanged
  boost → rerank → dedupe-by-parent pipeline runs on the fused pool.
  BM25-only candidates dense never retrieved *can* enter the pool (the
  spike's "zero complementary recall" pathway is open here).
- `--hybrid` on `evals.run_eval`. **Default search behavior is unchanged**
  — the dense/rerank-on run reproduces the committed
  [system-boost baseline](../../sidecar/evals/baselines/2026-07-09-system-boost.md)
  to the digit.

Corpus: the harness's three CC rulebooks (BFRPG, Black Flag, 5e SRD),
40 pre-registered queries. Baselines:
`sidecar/evals/baselines/2026-07-09-bm25-{dense,hybrid}-{rerank,norerank}.*`.

## Results

### Rerank on (production default)

| category | n | nDCG@10 | | MRR@5 | | recall@5 | | recall@10 | |
|---|---|---|---|---|---|---|---|---|---|
| | | dense | hybrid | dense | hybrid | dense | hybrid | dense | hybrid |
| cross_page | 3 | 0.877 | 0.877 | 0.833 | 0.833 | 1.000 | 1.000 | 1.000 | 1.000 |
| cross_system | 10 | 0.580 | 0.605 | 0.550 | 0.508 | 0.600 | **0.900** | 0.700 | **0.900** |
| prose | 11 | 0.459 | 0.396 | 0.321 | 0.273 | 0.727 | 0.636 | 0.818 | 0.727 |
| stat_block | 6 | 0.968 | 0.966 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| table | 10 | 0.648 | 0.611 | 0.583 | 0.533 | 0.800 | 0.800 | 0.900 | 0.900 |
| **all** | 40 | 0.644 | 0.624 | 0.584 | 0.548 | 0.775 | 0.825 | 0.850 | 0.875 |

(precision@5 all: 0.195 → 0.205; precision@10: 0.128 → 0.130)

### Rerank off

| category | n | nDCG@10 | | MRR@5 | | recall@5 | | recall@10 | |
|---|---|---|---|---|---|---|---|---|---|
| | | dense | hybrid | dense | hybrid | dense | hybrid | dense | hybrid |
| cross_page | 3 | 0.712 | **0.865** | 0.611 | **0.833** | 1.000 | 1.000 | 1.000 | 1.000 |
| cross_system | 10 | 0.759 | 0.677 | 0.750 | 0.583 | 0.800 | 0.800 | 0.800 | 0.900 |
| prose | 11 | 0.558 | 0.431 | 0.495 | 0.324 | 0.636 | 0.727 | 0.727 | 0.727 |
| stat_block | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| table | 10 | 0.724 | 0.723 | 0.700 | 0.658 | 0.800 | 0.800 | 0.900 | 0.900 |
| **all** | 40 | 0.727 | 0.683 | 0.695 | 0.612 | 0.800 | 0.825 | 0.850 | 0.875 |

(precision@5 all: 0.185 → 0.205; precision@10: 0.118 → 0.128)

## Reading

- **Hybrid does find answers dense misses** — the spike's "zero
  complementary recall" does not reproduce under answer-chunk grading.
  With rerank on, cross_system recall@5 jumps 0.600 → 0.900 and recall@10
  0.700 → 0.900; overall recall@5 +0.050, recall@10 +0.025, and precision
  ticks up. BM25 is doing exactly its job: pulling exact-token matches
  into the candidate pool.
- **But it costs ranking quality where it doesn't help.** Aggregate
  nDCG@10/MRR@5 regress in both configs (rerank on: −0.020/−0.036;
  rerank off: −0.044/−0.083), driven by prose (−0.063 nDCG rerank-on,
  −0.127 rerank-off) and table. Untuned 1:1 RRF lets keyword-dense but
  wrong chunks displace semantically-right ones near the top.
- **The pre-registered success criterion is not met.** The roadmap asked
  for complementary recall *or* a per-category lift **with no aggregate
  regression**. The recall gain is real, but the aggregate first-hit
  metrics regress in both configurations.
- Side observation, not this test's question: **rerank-off beats
  rerank-on** on this corpus for dense retrieval (nDCG 0.727 vs 0.644,
  MRR 0.695 vs 0.584) — more evidence for roadmap item #2 (the reranker
  was never validated and needs its own decision).

## Recommendation: NO-GO for default-on. Keep the flag.

Do not enable `hybrid` by default. On this corpus the untuned fusion
trades first-hit quality (what the GM sees at rank 1) for pool recall, and
loses the trade overall.

What this re-test still cannot answer — and what would change the verdict:

1. **French / OOV / homebrew queries** — the corpus and all 40 queries are
   English with in-vocabulary D&D proper nouns; the regime where BM25 is
   structurally strongest (and where the English-only reranker actively
   fails) remains untested. Roadmap item 16 (French queries in the
   harness, ideally over French/homebrew PDFs) is the prerequisite, and
   the `hybrid` flag + `--hybrid` ablation now make that re-test a
   one-command comparison.
2. **Tuned or gated fusion** — the recall signal suggests a
   dense-weighted RRF or gating BM25 to exact-token-heavy queries could
   keep the recall win without the prose/table regression. Only worth
   exploring after (1), and only if the multilingual result is promising.

The flag and the lexical index stay in the codebase as the measurement
instrument for that follow-up; they add no dependencies and change no
default behavior.

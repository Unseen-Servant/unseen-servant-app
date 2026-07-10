# Goal: Fix the live search bugs, then make search quality measurable

**Date:** 2026-07-09
**Derived from:** [2026-07-01 retrieval pipeline improvement roadmap](2026-07-01-retrieval-pipeline-improvement-roadmap.md)
**Framing:** Fix-first, then measure. Two phases, each with binary completion criteria.
**Status:** Phase 1 and Phase 2 shipped (2026-07-09).

---

## Phase 1 — Fix what's broken today — **SHIPPED**

Roadmap Tier 0 + Tier 1, issues [#304](https://github.com/Unseen-Servant/unseen-legend-lore/issues/304)–[#310](https://github.com/Unseen-Servant/unseen-legend-lore/issues/310). All seven are closed and on `main`, each with a repro test. All seven repros are mutation-verified as of 2026-07-09 — reverting the fix makes the covering test fail. #304, #305 and #309 were verified first; #306, #307, #308 and #310 followed, via five mutations (#308's collection and secondary-tag clauses are independent fix sites and were reverted separately).

1. **MCP search timeout** — explicit generous timeout, catch `TimeoutException`, surface a real error ([#304](https://github.com/Unseen-Servant/unseen-legend-lore/issues/304)) — `81eeb17`, `sidecar/tests/test_mcp_timeout.py`
2. **Reranker safety** — skip rerank for non-English queries; cosine fallback is already a tested path ([#305](https://github.com/Unseen-Servant/unseen-legend-lore/issues/305)) — `81eeb17`, `sidecar/tests/test_search_rerank.py`
3. **Reconcile relevance scores** — three incompatible scales (rerank sigmoid, `1−cosine`, saturated 0.999s) flow through one `relevance` field ([#306](https://github.com/Unseen-Servant/unseen-legend-lore/issues/306)) — `55d2e66`, `sidecar/tests/test_search_tiers.py`
4. **Untagged files survive muting** — muting one system no longer drops all `unknown`-tagged files from search ([#307](https://github.com/Unseen-Servant/unseen-legend-lore/issues/307)) — `374d668`, `src/lib/searchScope.test.ts` (the mute/solo rule is frontend-side)
5. **Collection scoping by path** — filter on the stored `source` path, not filename, so same-named books don't leak across systems ([#308](https://github.com/Unseen-Servant/unseen-legend-lore/issues/308)) — `374d668`, `sidecar/tests/test_search_scoping.py`
6. **MCP filter mismatches surface the reason** — validate/fuzzy-resolve filters against the manifest instead of reporting "not in library" ([#309](https://github.com/Unseen-Servant/unseen-legend-lore/issues/309)) — `7b9d997`, `sidecar/tests/test_filter_resolution.py`
7. **Relevance floor** — weak-match divider on scoped searches so wrong-system hits aren't returned with confidence ([#310](https://github.com/Unseen-Servant/unseen-legend-lore/issues/310)) — `55d2e66`, `sidecar/tests/test_search_tiers.py`

All fixes are query-side (#307 partly in the frontend scope filter); none required re-indexing.

### Known gap carried into Phase 2

The #305 reranker guard is `_rerank_safe_for_query() → query.isascii()`. It is deliberately conservative: it never changes English behaviour, and it catches French queries that carry an accent (`dégâts de chute`). It does **not** catch an unaccented French query (`comment fonctionnent les regles de chute`), which is all-ASCII and still hits the English-only cross-encoder.

Closing this properly means deciding rerank on / off / multilingual-model from data. Note the ordering trap: Phase 2 as scoped below is **English-only**, and an English-only harness cannot measure a French-query regression — so it will not settle this on its own. The gap closes only once the French eval queries listed under "out of scope" are added on top of the Phase 2 baseline. Until then the ASCII guard stays as a partial mitigation.

## Phase 2 — Stand up the eval harness in the production repo — **SHIPPED**

Roadmap item 16, descoped to English-only for now. Shipped 2026-07-09 as
[sidecar/evals/](../../sidecar/evals/README.md): `queries.yaml` (40 queries
ported from `hybrid_retrieval_spike`, now with answer anchors) + `scorer.py`
+ `run_eval.py`, one command (`uv run python -m evals.run_eval`), scorer
unit-tested in CI (`tests/test_eval_scorer.py`).

- ~~Port the harness (`queries.yaml` ground truth + scorer) from `unseen-legend-lore-experiments` into `sidecar/`~~
- ~~Score **nDCG@10, MRR@5, precision@k, recall@k**, reported **per query category** (stat block, table, prose, cross-page, cross-system) — graded on the specific answer chunk, not page overlap, since the page-overlap metric saturates~~
- ~~Runnable with one command against a defined corpus~~
- ~~Baseline results committed to the repo~~ — [2026-07-09 baseline](../../sidecar/evals/baselines/2026-07-09-baseline.md): nDCG@10 0.628, MRR@5 0.555, recall@10 0.850 overall (rerank on). Stat blocks are solved (MRR@5 1.000); the weak categories are prose (nDCG 0.459) and cross-system (nDCG 0.514 — three of ten unfiltered queries miss entirely, the gap the game-system soft-boost item targets). Two queries are structural zeros of the corpus, not retrieval failures: Black Flag never states the advantage/disadvantage core rule, and "Cleric saving throws at level 5" needs the p65 class-saves table that search doesn't surface in the top 10.

## Done when

- ~~All seven Phase 1 repros pass~~ — done; full sidecar suite green (492 passed)
- ~~The harness runs green with a committed baseline~~ — done (512 passed incl. scorer tests; baseline committed)
- CI is green on main

## Explicitly out of scope

Each of these becomes a follow-up goal that the baseline exists to serve:

- French/multilingual eval queries (additive later step, not a blocker)
- Tier 2 accuracy work (heading-promotion quality, two-column reading order)
- The BM25 / lexical hybrid re-test (reopened; needs the baseline first)
- Result-UX items (matched-span highlighting, stat-block stitching, open-at-page)

# Goal: Fix the live search bugs, then make search quality measurable

**Date:** 2026-07-09
**Derived from:** [2026-07-01 retrieval pipeline improvement roadmap](2026-07-01-retrieval-pipeline-improvement-roadmap.md)
**Framing:** Fix-first, then measure. Two phases, each with binary completion criteria.

---

## Phase 1 — Fix what's broken today

Roadmap Tier 0 + Tier 1, issues [#304](https://github.com/Unseen-Servant/unseen-legend-lore/issues/304)–[#310](https://github.com/Unseen-Servant/unseen-legend-lore/issues/310). Each item is done when a repro that fails today passes:

1. **MCP search timeout** — explicit generous timeout, catch `TimeoutException`, surface a real error ([#304](https://github.com/Unseen-Servant/unseen-legend-lore/issues/304))
2. **Reranker safety** — skip/flag rerank for non-English queries; cosine fallback is already a tested path ([#305](https://github.com/Unseen-Servant/unseen-legend-lore/issues/305))
3. **Reconcile relevance scores** — three incompatible scales (rerank sigmoid, `1−cosine`, saturated 0.999s) flow through one `relevance` field ([#306](https://github.com/Unseen-Servant/unseen-legend-lore/issues/306))
4. **Untagged files survive muting** — muting one system no longer drops all `unknown`-tagged files from search ([#307](https://github.com/Unseen-Servant/unseen-legend-lore/issues/307))
5. **Collection scoping by path** — filter on the stored `source` path, not filename, so same-named books don't leak across systems ([#308](https://github.com/Unseen-Servant/unseen-legend-lore/issues/308))
6. **MCP filter mismatches surface the reason** — validate/fuzzy-resolve filters against the manifest instead of reporting "not in library" ([#309](https://github.com/Unseen-Servant/unseen-legend-lore/issues/309))
7. **Relevance floor** — weak-match divider on scoped searches so wrong-system hits aren't returned with confidence ([#310](https://github.com/Unseen-Servant/unseen-legend-lore/issues/310))

All fixes are query-side; none require re-indexing.

## Phase 2 — Stand up the eval harness in the production repo

Roadmap item 16, descoped to English-only for now.

- Port the harness (`queries.yaml` ground truth + scorer) from `unseen-legend-lore-experiments` into `sidecar/`
- Score **nDCG@10, MRR@5, precision@k, recall@k**, reported **per query category** (stat block, table, prose, cross-page, cross-system) — graded on the specific answer chunk, not page overlap, since the page-overlap metric saturates
- Runnable with one command against a defined corpus
- Baseline results committed to the repo

## Done when

- All seven Phase 1 repros pass
- The harness runs green with a committed baseline
- CI is green on main

## Explicitly out of scope

Each of these becomes a follow-up goal that the baseline exists to serve:

- French/multilingual eval queries (additive later step, not a blocker)
- Tier 2 accuracy work (heading-promotion quality, two-column reading order)
- The BM25 / lexical hybrid re-test (reopened; needs the baseline first)
- Result-UX items (matched-span highlighting, stat-block stitching, open-at-page)

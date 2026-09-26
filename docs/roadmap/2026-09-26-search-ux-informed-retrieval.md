# Retrieval informed by how Legend Lore is searched

**Date:** 2026-09-26
**Status:** agreed 2026-09-26; item 1 (typing vs committing) landed 2026-09-26 (§6); item 2 measured and deprioritized the same day (§7).
**Context:** after the library store swap (`../retrieval/2026-09-26-library-store-design.md`) and the first library tier (`evals/baselines/2026-09-26-v2-library`). The goal is broad improvements, not tuning to a document: every item below is a *class* of behaviour, judged across both eval suites.

---

## 1. What the evals say, grouped by failure class

Both suites, 84 queries (`2026-09-26-v2-library-store`, 68 corpus; `2026-09-26-v2-library`, 16 on the real library):

| where #1 goes wrong | corpus | library |
|---|---|---|
| #1 correct | 56 | 8 |
| right book, wrong section | 8 | 5 |
| a different book | 2 | 3 |
| answer not retrieved at all | 2 | 0 |

- **Candidate generation is essentially solved:** 2 of 84 queries have no correct answer anywhere in the results.
- **Ordering sections inside the right book is where the losses are:** 13 of the 20 top-1 misses.
- **The reranker is confidently wrong:** a wrong #1 has median relevance 0.968 in the corpus (8 of 12 at ≥ 0.95), so the `strong` tier (≥ 0.98) cannot be read as "very likely right" while that holds.

Observed causes, each broader than the query that exposed it:

- **The system cue leaks into meaning.** A system named in the query is used for the boost, and also stays in the text that is embedded and reranked ("**dragon**bane fireball" ranks the DRAGON monster first).
- **Headings are trusted input, and some are wrong.** Units are embedded and reranked with their heading path prepended, so a wrong heading misleads actively. Seen in 4 of the 7 books inspected: gnome text under "Gnoll" (Basic Fantasy), Wight-Box monsters under "Level 5 Cleric Spells", Dragonbane Bestiary sections under NPC names, SRD combat rules under "Ability Scores and Modifiers".
- **The cross-encoder rewards word overlap and general sections.** MiniLM L-6 (web-search trained) decides the order alone; intro sections score 0.97–0.98 above the rule that answers.
- **A section ranks on its single best unit.** Several matching units earn a section nothing over one lucky sentence (hypothesis; least evidenced).

## 2. How the app is searched

From the code and the frontend design docs:

1. **Search runs as you type.** Every 300 ms pause (`Header.svelte` `DEBOUNCE_MS`) runs the full pipeline; Enter re-runs it. Most queries reaching the sidecar are partial.
2. **Scope lives on the console, not in the query.** Collections armed, systems soloed, folders muted resolve to `source_paths` and `game_systems`; 17 console actions re-run the current query. "Hold B to bypass" exists because the recurring question is *is my scope hiding it?*
3. **Results are a scrolling list of sections plus an inspector.** 25 per page up to 100; load-more re-runs the search with a larger `n_results`.
4. **Two searchers.** The GM in the app types short keyword queries scoped by the console: a glance at the top 1–3 at the table, scrolling and comparing during prep. Claude over MCP writes natural-language questions that name the system, mostly unscoped, reads 8 compact results and drills in with `get_section`.

Measured on the eval index, spell correction rewrites half-typed words into wrong ones: "grapp" → "grasp", "how do tro" → "how do to", "magic missi" → "magic miss". The full pipeline then searches for the rewritten query and shows its results while the GM is still typing.

## 3. Implications for retrieval

- **Typing and committing are different requests.** A trailing word typed mid-query is probably incomplete.
- **"Cued" is mostly Claude's regime.** In the app a system is soloed rather than typed, so cue leakage mainly hurts MCP queries. The app's regime is scoped search, which reduces most problems to ordering sections within a few books.
- **The evals do not mirror the console.** The library tier is unscoped and the corpus suite scopes only to a single book; nothing measures a 2–3-book collection scope, the common case at the table.
- **The metric should follow the moment.** At the table: success@1 and p95 latency on short scoped queries. In prep: recall and edition comparison.
- **Headings are display as well as ranking.** The result list shows the heading path, so a mis-headed chunk ranks wrong and is titled wrong.
- **Load-more may reorder rows already seen.** A larger `n_results` widens the dense candidate pool (`n_results × 10`); unverified.

## 4. Investigations, in order

| # | Item | Measured by | Notes |
|---|---|---|---|
| 1 | **Typing vs committing** (done, §6). A `partial` search request: the trailing word is completed from the vocabulary instead of spell-corrected, and prefix-matched in BM25 (FTS5 `term*`). The UI sends it for debounced searches whose raw text does not end in whitespace; Enter commits. | A prefix variant of both suites (each query's last word cut to a fixed share of its length), current vs partial mode; committed queries must be byte-identical to today. | Broad, cheap, and fixes a visible defect. Skipping the reranker while typing is a follow-up only if latency needs it: a debounced search is often the final one (many searches never see Enter). |
| 2 | **Ordering within a book under scope** (measured, little headroom — §7). Candidates: section-level evidence (best + second-best unit), heading trust. | Collection-scoped library queries (2–3 books), authored and committed *before* any fix is tried. | The regime the app is used in. |
| 3 | **Heading quality.** Measure mis-heading across the real library (`breadcrumb_qa`-style checks), then fix in extraction. | Per-book flaw counts, then both suites. | Worth more than its eval impact alone: headings are shown to the user. |
| 4 | **Cue stripping + reranker choice.** Remove a detected system cue from the text embedded and reranked; compare MiniLM L-6 with `bge-reranker-v2-m3`. | MCP-shaped (NL, system named, unscoped) queries in both suites; latency budget. | Folded into the runtime-swap benchmark (`2026-09-26-ml-runtime-consolidation.md`), where the reranker runtime is decided anyway. |

Also open, not scheduled: load-more stability (item-sized check: top 25 at `n_results` 25 vs 50); "N strong hits outside your scope" as an answer to the bypass question (a feature, not a fix).

## 5. Rules for these investigations

- **Judge by class, not by query.** A change is kept when its class improves across both suites with no unexplained per-query loss, not when one query flips.
- **Pre-register queries.** Before trying a fix for a class, author 2–3 new queries for that class and commit them first, so the fix is measured on queries it was not designed around.
- **Usage over guesses.** A local, opt-in search log (a plain `search_log.jsonl` in the data dir: query, scope, source app/MCP, top results; then reformulations, load-more, MCP drill-ins) would rank these classes by how often they occur in real sessions and supply library-tier queries from real failures. Proposed, not built: stage 1 is sidecar-only with no UI instrumentation; stage 2 (result opens, PDF jumps, a one-key "this answered it" mark) only if stage 1 proves useful.

## 6. Item 1 result — typing vs committing (2026-09-26)

**Harness:** `run_eval --prefix FRAC` cuts each query's last word to FRAC of its length (≥ 3 letters, words of 5+ letters only, trailing punctuation dropped — `evals/retrieval/prefixes.py`); `--partial` sends the new request field. At 0.5, 49 of 68 corpus and 14 of 16 library queries end mid-word.

**Finding that changed the design.** At a half-typed word, today's edit-distance correction is never right: of the 49 cut words it produced the intended word 0 times and a wrong one 18 times ("wea" → "sea", "cai" → "can", "fant" → "ant", "rou" → "you"). Only protecting the word from correction left ranking flat (all MRR@5 0.797 → 0.797). Completing it from the library's vocabulary gave the intended word 35 of 49 times, most misses being inflections ("walls" → "wall"); scoring candidates with the existing neighbour context fixes the rest seen ("against poi" → "poison", "year zero eng" → "engine", "determined in com" → "combat").

**Shipped:** `SearchRequest.partial`. The trailing word is protected from correction, completed by `SpellCorrector.complete` (most frequent in-vocab words with the prefix, the left neighbour's context score decides), and matched as an FTS5 prefix term; completion is silent (no `message`) and reported as `completed_query`. The app sends `partial` for a debounced search whose raw text doesn't end in whitespace; Enter commits without it; scope toggles and load-more re-send the last search's flag.

| MRR@5 on half-typed queries | today | protect only | complete + prefix | finished queries |
|---|---|---|---|---|
| corpus, all | 0.797 | 0.797 | **0.848** | 0.876 |
| corpus, cued | 0.597 | 0.597 | **0.694** | 0.750 |
| corpus, uncued | 0.854 | 0.879 | **0.938** | 0.942 |
| corpus, single | 0.948 | 0.927 | 0.927 | 0.948 |
| library, all | 0.578 | — | **0.740** | 0.695 |

Closes about 65 % of the corpus typing gap. 9 corpus queries better, 3 worse, all explained: q019 returns to its committed-query loss (the mis-headed gnoll chunk), q042 is a near-tie among ancient dragons once "breath wea" completes to "breath weapon" (today's "breath sea" was accidentally narrower), q050 completes correctly but stays below the top 5 (the reranker's pull to intro sections, item 4). Committed queries (partial off) reproduce `2026-09-26-v2-library-store` exactly.

## 7. Item 2 result — ordering within a book under scope (2026-09-26)

Nine keyword/NL pairs scoped to the three Dragonbane books (the collection Jerome arms together), sent as `source_paths` the way the console does, pre-registered in `0e2a9cb` before any fix: sections drawn with `random.Random(20260926)` from all 832 Dragonbane sections of ≥ 300 chars, three per book, questions written from the drawn text.

**Baseline `2026-09-26-v2-library-scoped` (the whole library tier, 34 queries, hybrid):** collection MRR@5 **0.972** (17 of 18 at #1), cued 0.635, uncued 0.875, all 0.842; p50 285 ms. The one miss (L113, "pit of skeletons fear roll") ranks another adventure's Sacrificial Pit first — a fair ambiguity; its NL twin is #1.

**Conclusion:** under the console's scope, within-book ordering has almost no headroom. The "right book, wrong section" misses of §1 come from unscoped searches, which the console normally prevents, so item 2 is not worth a fix now. Caveat: questions written from the drawn text share its vocabulary; the NL versions finding the answer at #1 suggests that is not the whole story. The remaining losses sit in unscoped search — mostly the MCP regime and unscoped app searches — which points at items 3 (headings) and 4 (cue stripping, reranker).


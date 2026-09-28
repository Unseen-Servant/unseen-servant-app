# Retrieval informed by how Legend Lore is searched

**Date:** 2026-09-26
**Status:** agreed 2026-09-26; item 1 (typing vs committing) landed 2026-09-26 (§6); item 2 measured and deprioritized the same day (§7); item 4's cue stripping landed the same day (§8), its reranker choice is still open; item 3 (heading quality) started 2026-09-27.; item 3 closed 2026-09-27 (§11): junk filter kept, outline and entry-name headings NO-GO
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
| 3 | **Heading quality** (in progress). Measure mis-heading across the real library (`breadcrumb_qa`-style checks), then fix in extraction. | Per-book flaw counts, then both suites. | Worth more than its eval impact alone: headings are shown to the user. |
| 4 | **Cue stripping + reranker choice.** Remove a detected system cue from the text embedded and reranked; compare MiniLM L-6 with `bge-reranker-v2-m3`. | MCP-shaped (NL, system named, unscoped) queries in both suites; latency budget. | Cue stripping done (§8). Reranker choice folded into the runtime-swap benchmark (`2026-09-26-ml-runtime-consolidation.md`), where the reranker runtime is decided anyway. |

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

## 8. Item 4 result — cue stripping (2026-09-26)

**Shipped:** a system named in the query is left out of the text that is embedded, BM25-matched and reranked; system detection and the boost still read the whole query (`strip_system_cues`, next to `detect_systems_in_query`). Only whole words that normalize to a system keyword are removed ("dnd 5e", "D&D", "dragon bane", "osric's"). A cue that detection finds only as a substring straddling words still boosts but stays in the text, and a query that is nothing but a cue is searched as typed. `SearchRequest.strip_cues` is request-only and on by default; `run_eval --keep-cues` restores the old behaviour.

**Pre-registered** in `31dc506`, before the fix: three cued pairs (L017–L022) drawn with `random.Random(20260926)` from OSRIC, the Dragonbane Rulebook and SRD 5.1, each a topic another book of the library also covers. All six were already #1 with the cue kept and stay #1, so they show the fix costs nothing on unseen queries but not that it helps them.

| MRR@5 | cue kept | cue stripped |
|---|---|---|
| library, cued (18) | 0.756 | **0.972** |
| corpus, cued (24) | 0.750 | **0.806** |
| library, all (40) | 0.865 | **0.963** |
| corpus, all (68) | 0.876 | **0.896** |

Every other scope is identical in both runs: no cue, no change. Latency is unchanged. Baselines: `2026-09-26-v2-library-cue-strip`, `2026-09-26-v2-cue-strip`.

- **Library:** 7 better, none worse. All six original Dragonbane queries reach #1: "dragonbane fireball" no longer ranks the DRAGON monster first, and "how many items can a character carry in dragonbane?" goes from #5 to #1. "osric morale check" goes from #3 to #1.
- **Corpus:** 6 better, 2 worse. Better: "year zero engine initiative" (q049 #9 → #1, q050 #25 → #2), and q018–q020 from #2 to #1. Worse: q045/q046, Basic Fantasy magic missile, #1 → #6/#3. **The cause is item 3's class:** Magic Missile has no heading of its own in the extraction. It sits inside a 5,079-char section titled "Hallucinatory Terrain > BASIC FANTASY RPG", where the page footer was promoted to a heading. The query's "basic fantasy" matching that bogus heading is what put it first. It was right for the wrong reason, and a heading fix is what should bring it back.

Still open in item 4: the reranker choice (MiniLM L-6 vs `bge-reranker-v2-m3`), in the runtime-swap benchmark.

## 9. Item 3 measurement — how often headings are wrong (2026-09-27)

**Method.** 40 units per book drawn with `random.Random(20260927)` from Jerome's library store (240 units, weighted by units, i.e. by text volume), each labelled against a fixed rubric by one of three agents (two books each): ok, wrong_entry (the text belongs to another entry), wrong_parent (a wrong ancestor), attribution (a quote/speaker/stat line promoted to a heading), lost_context (the path cannot say what the text belongs to), garbled, furniture, no_heading. A random dozen spot-checked by hand agreed. Sample and labels are local (`evals/.eval_data/heading_audit/`, gitignored — they contain book text) so the same texts can be re-judged after a fix.

| book | mis-headed | wrong_parent | wrong_entry | attribution | lost_context | other |
|---|---|---|---|---|---|---|
| Dragonbane Bestiary | 23/40 | 12 | 6 | 8 | 0 | 0 |
| Dragonbane Adventures | 14/40 | 6 | 6 | 1 | 8 | 0 |
| Dragonbane Rulebook | 22/40 | 13 | 15 | 1 | 1 | 2 |
| OSRIC 2E | 7/40 | 5 | 3 | 0 | 0 | 0 |
| SRD 5.1 | 16/40 | 14 | 2 | 0 | 2 | 0 |
| Wight-Box | 40/40 | 2 | 34 | 13 | 2 | 11 |
| **all** | **122/240 (51 %)** | 52 | 66 | 23 | 13 | 12 |

Weighted by book size, about **33 %** of the library's units carry a misleading heading. The existing `breadcrumb_qa` checks (markup, split letters, mixed case, furniture root, no heading) flag 0.3–7.2 % per book: they measure typographic damage, which the Phase-1 heading work fixed, not attribution.

**Mechanisms** (from `promote_headings.py` and the chunker's heading stack). Headings are what pymupdf4llm marks by font; levels come from font-signature clusters, with the PDF outline used only for depth-1 chapters; the chunker's stack closes a parent only when a heading of the same or higher level appears. Hence:

1. **A missed chapter heading leaves the previous parent open indefinitely** — "MENTALISM" over the Rulebook's whole Gear chapter (pp. 77–84), "Level 5 Cleric Spells" over Wight-Box pp. 45–150, "Ability Scores and Modifiers" over SRD travel and combat rules, "Paired Items" over every SRD magic item. Most wrong_parent.
2. **A missed entry heading merges its text into the previous entry** — a thunderstroke spell under "RESURRECTION", Fire Blast under "GUST OF WIND", Bandits under a spell list. Most wrong_entry.
3. **Bold lines promoted to headings** — quote attributions ("– Kaspert Woodshot, gamekeeper"), stat lines ("Ferocity: 2 Size: Small", "Armor Class 11"), read-aloud sentences, sentence fragments ("wights."). All attribution.
4. **Sidebars treated as parents** — the Bestiary's Random Encounter / Adventure Seed sidebars become ancestors of the monster's attacks and traits.

**The general remedy available:** five of the six books ship a detailed PDF outline (OSRIC 1,228 entries to depth 6; Dragonbane Rulebook 659, Adventures 444, Bestiary 360 with an entry per monster; Wight-Box 192). The Dragonbane outlines even label sidebars ("Sidebar: …", "Table: …"). Only SRD 5.1 has none (two file-level entries). An outline is the publisher's own structure with page positions, so ancestors taken from the outline entries covering a text's position cannot stay open past the next chapter, and each entry it lists cannot be missed.

## 10. Are headings worth it in ranking? — ablation (2026-09-27)

**Question** (Jerome): with a third of the library mis-headed, is putting headings into ranking worth the complexity, or could hybrid BM25 cover for leaving them out of the embeddings and the reranker?

**Method.** Eval-only switches in `service.py` (`HEADING_EMBED`, `HEADING_FTS`, `HEADING_RERANK`: `path` = production, `leaf`, `none`; embeddings and BM25 fixed at index time, the reranker per query). A fresh index per variant for the corpus suite and for a copy of Jerome's six books built from the PDFs on disk (the app's index untouched), with his custom game systems and tags copied so the boost and scope match the app. Hybrid on, cue stripping on, everything else as shipped. Variant A is the existing references.

| MRR@5 | A: full path (today) | B: none in vectors/reranker, full path in BM25 | C: none anywhere | D: leaf only |
|---|---|---|---|---|
| corpus (68) | **0.896** | 0.775 | 0.776 | 0.853 |
| corpus, single-book | **0.948** | 0.733 | 0.736 | 0.826 |
| library (40) | 0.963 | 0.810 | 0.815 | **0.975** |
| library, collection-scoped | 0.972 | 0.796 | 0.796 | 0.972 |

**Findings.**

- **Headings are one of the strongest ranking signals, even this broken.** Taking them out of the vectors and the reranker costs about 0.12 on the corpus and 0.15 on the library. B loses 12 corpus and 9 library queries and wins 3 and 0.
- **Titles in BM25 alone do not compensate** (B ≈ C). BM25 can bring a stat-table row into the pool, but the reranker then judges it without the name.
- **What the heading carries that the body does not is the entity's name.** Every loss names one: "goblin warrior hit points" (#1 → not found), "twin shot heroic ability" (#1 → not found), "adult black dragon attacks" (#1 → #13), "ancient gold dragon armor class" (#1 → #22), fireball, magic missile, the Tower of Sacrifice demon. A stat block's or spell's body never repeats its name.
- **Ancestors help when right and cost a little when wrong.** Leaf-only trails the full path on the corpus (decent headings; 7 worse, 3 better, mostly #1 → #2 where the leaf is a generic "Actions" and the name sits in the ancestor) and edges it on the library (bad headings; 0 worse, 1 better). The queries leaf-only wins are the misleading-ancestor cases ("osric falling damage", both Year Zero initiative queries).

**Conclusion.** Keep headings in ranking; the item-3 direction is to make them *correct*, not to use less of them. That supports the outline design (`../retrieval/2026-09-27-outline-headings-design.md`): its main effects — no stale ancestors, no missed entry names — are exactly the two things this ablation shows matter. Not adopted: switching production to leaf-only (a corpus loss for a one-query library gain). A cheap follow-up worth one run after the outline work: prepend the nearest *named* segment rather than the raw leaf ("Ancient Gold Dragon", not "Actions"). The switches stay in the code so the same ablation can be re-run on corrected headings.

## 11. Item 3 closed — what shipped and what did not (2026-09-27)

| change | outcome | evidence |
|---|---|---|
| **Junk filter** (bb0922f): quote attributions, Label: value stat lines and sentences stop being headings | **kept** | Rejects only non-titles across 5,528 real heading segments; touches 32 % of the Dragonbane Bestiary's units and 37 % of Wight-Box's. Retrieval-neutral: the corpus suite reproduces `2026-09-26-v2-cue-strip` exactly, and a fresh library copy scores 0.963 (= the reference). Its value is in the titles shown and in section boundaries; it ships with `CHUNKER_VERSION` v4 and reaches the library on the next reindex. |
| **Outline headings** (a27b898, `strategy="outline"`) | **NO-GO as default** (5cf8b5c), code kept | Collection sample 40.3 % → 39.5 % mis-headed (10 fixed, 8 broken); corpus 0.896 → 0.893 (single-book −0.10); breadcrumb split-letter rise. Details in `../retrieval/2026-09-27-outline-headings-design.md` §8. |
| **Entry-name headings** — the heading from one level above the entry's name down, higher ancestors dropped; a segment is a generic label when it sits under ≥ 3 ancestor paths in its book | **NO-GO**, not kept | Corpus 0.896 → 0.888 (2 worse, 1 better), library 0.963 → 0.950 (1 worse), all #1 ↔ #2 flips: the dropped ancestors carried useful context more often than they misled. |

**Conclusion.** For ranking, the full heading path stays the best of every variant measured (full, BM25-only, none, leaf, entry, outline-structured). About 40 % of passages across a random slice of the collection still carry a misleading heading, but the retrieval suites are not sensitive to most of it; the remaining cost is mostly in what the user sees (result titles, section boundaries, `get_section` spans). The causes the outline did not reach — headings shifted by one entry, neighbouring entries named, siblings nested by font level, TOC and credits lines as headings — are extraction problems for a later pass, best started from the collection sample's labelled examples (`evals/.eval_data/outline_validation/`, now a development set).


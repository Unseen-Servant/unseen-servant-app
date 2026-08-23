# v3 Search — Recovery Strategy After the Phase 3 Roadblock

**Date:** 2026-08-22
**Status:** proposal — awaiting Jerome's call before any code.
**Supersedes nothing.** Amends the execution order of [2026-08-13-pipeline-rebuild-plan.md](2026-08-13-pipeline-rebuild-plan.md) (Phases 2–4) in light of what Phase 3 measured.
**Objective (unchanged):** a retrieval pipeline that is much faster *and* much more relevant than v2, for the app UI, Claude, and 4B-class local models.

---

## 0. TL;DR

- **The v3 query stack works.** Latency 244 ms p50 vs v2's 1 464 ms (6×), cued disambiguation 0.592 vs 0.519, payload −43 %, typo tolerance, one SQLite file, no Ollama. Keep all of it.
- **The v3 ingestion stack is what broke the blind round** — and it is one defect, not many: PP-DocLayout-M **misses half the text on dense TTRPG pages** (53 % of spans uncovered on the SRD goblin page, 64 % on an OSRIC two-column prose page — it found no right-column region at all). Every "fix" so far was a smarter way to guess where the uncovered text belongs, and every guess manufactures interleaved columns, torn label/value pairs, or headings glued to the wrong body. That is the exact R1 defect v3 was built to kill, re-created one stage later.
- **The ranking stack is not the gap.** Of the 20 queries where v3 trails v2, the 8 hard misses are all scrambled-extraction cases; the rest are rank 1→2 flips. Where extraction is clean, v3 ≥ v2.
- **Strategy:** stop treating the layout model as the *text carrier*. PyMuPDF's native blocks are column-correct on every page we inspected; the model should only *classify* (table / heading / furniture) and *order*, never cut text. Build the corpus-wide extraction gate the 30-page golden set cannot be, make that the inner loop (5 min, no embedding) instead of the 48-min reindex, then finish the two unbuilt pieces of the plan that the eval gap is actually pointing at (section parents with a token budget; cross-page stitching), and only then re-open ranking polish.
- **Cutover bar:** human-scored single ≥ v2's 0.87, auto all-MRR@5 ≥ 0.70, zero unreadable chunks in the blind top-5, p50 ≤ 300 ms.

---

## 1. Where we actually are

### 1.1 Scoreboard (auto-graded, 68 queries, 7 books)

| | v2 phase0 (08-15) | v3 full stack (08-19) | verdict |
|---|---|---|---|
| all MRR@5 | **0.701** | 0.614 | v2 |
| single (book selected — the common path) | **0.683** | 0.460 | v2, −0.22 |
| cued (query names the system) | 0.519 | **0.592** | v3 |
| uncued | **0.942** | 0.825 | v2 |
| recall@3 all | **0.750** | 0.706 | v2 |
| payload chars / call | 36 928 | **21 137** | v3, −43 % |
| latency p50 / p95 | 1 464 / 1 896 ms | **244 / 361 ms** | v3, 6× |
| cross_page | 0.000 | 0.000 | both fail ([#375](https://github.com/Unseen-Servant/unseen-legend-lore/issues/375)) |

Per query, v3 is better on 11, worse on 20, equal on 37. The 20 "worse" split cleanly: **8 hard misses** (q001/q002 goblin AC, q004 fireball, q010 plate armor, q016 thief table, q025 paladin lay-on-hands, q046 BFRPG magic missile, q047 OSRIC surprise) and **12 rank 1→2 flips** (rerank/RRF noise, worth ~0.03 MRR in aggregate).

### 1.2 What happened in the blind round

Two separate things, both now understood:

1. **The 08-17 sheet was invalid.** The SRD embeds `\t\r\xa0` runs between tokens; v3 normalised the *embedded unit* text incidentally but stored the *parent chunk* raw, so every SRD payload read as litter. Fixed at the span source (`f4b7471`), reindexed 08-19. Auto numbers unchanged (the grader strips punctuation anyway); readability restored.
2. **Monster stat blocks and two-column prose are still scrambled on the 08-19 sheet.** The row-coherent attach (`9171f00`) fixed the one golden page it targeted (g28 0.5 → 1.0) and moved 15 other queries (8 up, 7 down, net flat). It did *not* fix the goblin query — q001/q002 are still misses — because the goblin's own AC line is now fused with the hobgoblin's from the other column.

So the user's perception was correct on both counts: the sheet was unreadable, and the stat-block parsing regressed against the v2 round. Both trace to the same stage.

### 1.3 The mechanism, verified on real pages

Running the shipped Stage B on the two pages behind the worst misses:

| page | spans | **uncovered by any region** | uncovered rows that span both columns |
|---|---|---|---|
| SRD 5.1 p315 (Goblin / Hobgoblin) | 166 | **88 (53 %)** | 8 |
| OSRIC p156 (two-column prose) | 126 | **81 (64 %)** — model found 3 left-column regions, none on the right | 21 |

What the shipped assembly then emits for the goblin:

```
Skills Stealth +6
Armor Class 15 (chain shirt) Senses darkvision 60 ft., passive Perception 9   ← hobgoblin AC ‖ goblin senses
Hit Points 16 (3d6 + 6) Languages Common, Goblin
```

and for OSRIC:

```
Normally the GM rolls this die in secret, because the player check and success by either indicates the door opens. If the
```

PyMuPDF's native `get_text("blocks")` on the same pages is column-correct (`x[58,277]` blocks on the left, `x[306,554]` on the right, never merged). The interleave is not in the PDF and not in Stage A; it is created by `_rows(uncovered)` grouping spans by *y* across the full page width, then attaching each row to the nearest region.

Corpus-wide, shipped model, layout stage only (≈ 6.5 min for the whole corpus — this is the inner loop W0/W1 should run on):

| book | pages | mean uncovered span frac | pages > 30 % uncovered | pages with cross-column row merges | cross-column rows | PyMuPDF wide-block frac |
|---|---|---|---|---|---|---|
| srd_5_1 | 403 | 0.21 | **119** | **141** | 827 | 0.004 |
| srd_5_2_1 | 364 | 0.22 | **114** | **112** | 435 | 0.031 |
| osric_2e | 381 | 0.17 | 66 | **113** | **1 606** | 0.119 |
| black_hack_1e | 20 | 0.20 | 4 | 3 | 96 | 0.294 (single-column booklet — wide is legitimate) |
| cairn_1e | 20 | 0.19 | 3 | 5 | 76 | 0.076 |
| bfrpg_4e | 207 | 0.03 | 1 | 12 | 74 | 0.092 |
| yze_srd | 45 | 0.05 | 0 | 5 | 5 | 0.119 |
| **total** | **1 440** | | **307 (21 %)** | **391 (27 %)** | 3 119 | |

Read: one page in five loses a third or more of its text to the detection gap, one in four gets cross-column rows manufactured, and the damage sits in the three books a GM queries most. PyMuPDF's own blocks are almost never column-merged on the SRDs (0.4 % / 3 %); OSRIC's 12 % wide blocks are the population W1.3's per-page fallback exists for and W0.1 will characterise.

### 1.4 Why the harness kept saying GO

The extraction gate is 30 hand-picked pages, reported as a mean. The goblin page sat at 0.5 inside a 0.94 aggregate that "beat v2's 0.935"; the OSRIC interleave page was never a golden page. The 08-17 follow-up fixed g28 and the aggregate rose to 0.976 — while the real chunk for the same monster got *worse*. This is the third time the eval-harness-limits pattern has bitten (rerank 07-10, conditioning 08-17, layout 08-19): **a 30-page mean cannot see a defect that lives on 30 % of the pages of one book.** The retrieval suite then grades ranking over whatever units exist, so scrambled units that still contain the anchor tokens pass, and readable units that lost a label fail. Neither axis measures what the GM sees.

### 1.5 What is *not* broken

- Stage A (PyMuPDF spans) is clean and complete.
- The layout model's *classification* is valuable: table regions drove the +72 % table_lookup win, heading regions drove heading-prepend (0.165 → 0.370), furniture drop keeps payloads compact and kills v2's `CONTENTS >` / running-header breadcrumbs ([#328](https://github.com/Unseen-Servant/unseen-legend-lore/issues/328), [#367](https://github.com/Unseen-Servant/unseen-legend-lore/issues/367)).
- Every query-side rung paid on the harness and the stack as a whole is inside the latency budget. The v2 breadcrumbs it replaces are genuinely bad (`**S eed** **<u>p</u>** > **Goblin**`, `fOR fRee UpdateS, eRRata…` as OSRIC's root) — v3's are clean titles.
- sqlite-vec, the fp32 bge-m3 ONNX embedder (perfect parity with Ollama), MiniLM rerank latency: all Phase 1 gates hold.

---

## 2. Principles for the recovery

1. **Text comes from the PDF's own structure; models only label it.** PyMuPDF lines and blocks are the atomic text units. A layout region may *type* a block and *order* blocks; it may never split a line or merge lines from two blocks. "Correct-ugly beats wrong-clean" — the glm_ocr lesson, applied to our own layout stage.
2. **Gate on the worst page, not the mean page.** Per-page no-regression is the rule for extraction; aggregates are for the report.
3. **The inner loop must be minutes, not an hour.** Extraction + layout over the whole corpus is ~5 min with no embedding. Iterate there; reindex only when extraction is green.
4. **Readability is a graded property.** The blind sheet gets a per-chunk "readable?" tick. A chunk the GM cannot read is a miss whatever the anchors say.
5. **Compactness is a budget, not a chunk size.** Serve section parents; let the consumer's `max_context_chars` decide how much ships. Don't shrink parents to win a payload column.

---

## 3. Approaches considered

**A. Keep patching span assignment in Stage B** (smarter uncovered-span heuristics: column-aware row grouping, region dilation, stat-block detectors).
*For:* smallest diff each time. *Against:* this is what we have been doing; each patch fixed one page and moved fifteen queries; the defect is detection recall (50–65 % of spans uncovered), and no assignment heuristic recovers structure the model never saw. Whack-a-mole with a 48-min test cycle. **Not recommended.**

**B. PyMuPDF blocks carry the text; the layout model classifies and orders.** (Recommended — §4 W1.)
*For:* kills interleave and label-tearing by construction (lines are never re-formed), keeps every model-driven win (table typing, heading typing, furniture), keeps bbox provenance and the typed IR, no model swap, no new dependency. *Against:* tables inside a region still need cell inference (today's gap heuristic, or `page.find_tables(clip=…)` for ruled tables); PyMuPDF blocks can themselves be wrong on a few exotic layouts — hence the per-page fallback in W1.3.

**C. Use pymupdf4llm (v2 extraction) as the text source under the v3 query stack.**
*For:* known-readable stat blocks and tables; one day of work. *Against:* re-inherits Markdown-as-IR (loses bbox, brings back `<br>` flattening and regex cleanup), re-inherits v2's heading damage and its own two-column interleave ([#329](https://github.com/Unseen-Servant/unseen-legend-lore/issues/329)), and contradicts constitution #6. **Keep as the time-boxed fallback only** if B fails its gate.

---

## 4. The plan

Ordered by dependency, not by how exciting the work is. Every item has a verify step; nothing lands without it.

### W0 — Make the harness able to see the defect (≈ 2 days, do first)

| # | change | verify |
|---|---|---|
| W0.1 | **Corpus-wide extraction QA** (`evals/extraction/corpus_qa.py`, `--suite corpus-qa`, shipped 2026-08-22). Engine-agnostic; the oracle is the PDF's own PyMuPDF text blocks, so no spec is needed. Per page: **block integrity** (native block ≥ 120 chars survives contiguously — *broken* = lines present but not contiguous, the interleave signature; *missing* = dropped, which is recall not integrity), **label lines** (`Armor Class 15 …`, `Range: …` survive whole), and **adjacency** (stacked neighbouring blocks stay consecutive — catches a stat line that is intact but glued under another creature). Per-book table + 20 worst pages; engine page texts saved to a gitignored `.pages.json` so drill-ins are instant. ~7 min per engine, no embedding. The Stage-B-internal uncovered-span fraction stayed a throwaway diagnostic (§1.3) — after W1 it has no meaning. | **Done:** OSRIC p156 is v3's #1 worst page (13/13 broken) while v2 scores 13/13 intact there; SRD 5.2.1 p183 v3 0/10 vs v2 9/10 — and the goblin page shows 10 of 37 neighbours displaced. Corpus: v3 block_integrity 0.764 vs v2 0.891, adjacency 0.924 vs 0.970; 691 vs 573 pages with a broken block. Surfaced two more defects: **SRD 5.2.1 paragraphs come out line-reordered *within* a column** on 321 of 364 pages (integrity 0.434), and **33 pages are emitted blank** (v2: 0) — the model detected only the footer, so with no content region to attach to, every span was dropped: OSRIC contents/encounter-table/license pages, Cairn pp. 9–12, a 5.2.1 spell table. Baselines `2026-08-22-{v2,v3}-corpus-qa`. |
| W0.2 | **Per-page min gate** on the golden set (`evals/extraction/gate.py`, `--suite extraction --gate <reference>.json`, shipped 2026-08-23): every page's every metric is compared to the reference baseline; any drop fails the run (exit 1), whatever the mean does. | **Done.** The historical check is a unit test: the 08-16 v3 baseline gated against v2 reports g28 `table_cells` 1.0 → 0.5. Live run on current v3 (`2026-08-23-v3-extraction`): vs 08-16 no regressions and g28 back to 1.0; vs **v2 it fails on g26** (OSRIC prose content_recall 1.000 → 0.667) — the page the "0.989 vs 0.993 near-miss" mean had hidden since 08-16. g26 joins W1's verify list. |
| W0.3 | **Add the missing regimes as golden pages** (+10, g31–g40, shipped 2026-08-23): SRD 5.1 Young White Dragon (p290), the Ancient Gold Dragon continuation (p299, the cross_page block), spell areas of effect (p103); OSRIC two-column prose (p156, p163) and the blank dinosaur tables (p202); SRD 5.2.1 blank bard spell lists (p34) and the line-reordered glossary (p183); Cairn's blank spellbook and equipment lists (p10, p11). YZE's blank chase table has no counterpart in its reference, so it cannot be golden. Picking pages exposed a 27-min verifier run: the reference stripper's `<(script\|style)` scanned to EOF for each of the BFRPG ODT's 9,483 `<style:style>` tags — fixed (1.6 s), with a test. | **Done.** All 40 verified ref ∧ PDF. Baselines `2026-08-23-{v2,v3}-extraction` (40 pages): v3 content 0.904 / order 0.907 / cells **0.772** (was 0.976 on 30 pages) vs v2 0.995 / 1.000 / 0.941. Gate v3→v2: **12 regressions on 8 pages** — blank pages g36/g39/g40 at 0.0, g37 0.5/0.0, two-column order g34 0.62 and g35 0.40, glossary order g38 0.87, g26 0.667. g31/g33 score 1.0 here despite corpus-qa flags (golden checks are coarser) — both instruments stay. |
| W0.4 | **Readability tick** in the blind scoresheet (per chunk: a second "garbled" toggle beside "relevant"; readable is the default so scoring effort is unchanged) and `readable@5` = 1 − garbled/top per query in `score.py`, per scope, plus the list of garbled chunks. Exports from before the tick score `—`, never 1.0. Shipped 2026-08-23. | **Done.** 08-19 v3 sheet regenerated with the tick (`…-rerank-srcfilter.blind.html`); v2's 08-15 labels re-score with readability `—`. The v3 round is still pending Jerome's scoring — and W1 reindexes before that, so the round should run on the post-W1 index. |
| W0.5 | `index_document` skips on PDF hash only; make it also compare `pipeline_version` so a code change invalidates the idempotent skip (the 08-19 `rm -rf` was a symptom). | test: bump version → re-index happens |

### W1 — Extraction: PyMuPDF blocks as the text carrier (≈ 1 week incl. two reindexes)

| # | change | verify |
|---|---|---|
| W1.1 | **Stage A emits lines and blocks, not just spans** (`get_text("dict")` already has them; keep span font stats per line). | unit tests: a block's lines are never split across Blocks downstream |
| W1.2 | **Stage B assigns PyMuPDF *blocks* to regions by area overlap** (majority of the block's bbox inside a region → that region's kind; else the block is `prose`). Text inside a block is PyMuPDF's own line order. Blocks are ordered by a column-aware XY-cut over block bboxes (the existing `_xy_cut`, now on blocks). Rows are only ever formed *inside* a `table` region, from lines whose block lies in that region; `_cells` stays as the gap heuristic, with `page.find_tables(clip=region)` tried first for ruled tables. Headings: a `paragraph_title` region types the block it covers; it never absorbs neighbouring blocks (today's "Gnome Cunning … Clay Golem … Large construct" heading). | golden set: `--gate 2026-08-23-v3-extraction.json` passes AND `--gate 2026-08-15-v2-extraction.json` passes (g26 recovers); corpus-qa: OSRIC p156 / SRD 5.2.1 p183 intact, goblin p315 adjacency ≥ v2, `pages_empty` 33 → 0, block_integrity ≥ v2's 0.891 per book; layout latency unchanged (model call is the same) |
| W1.3 | **Per-page fallback (plan §5, never built):** if W0.1's interleave_score for a page exceeds a threshold *after* W1.2 (PyMuPDF blocks themselves wrong), emit the page in PyMuPDF native order with no typing. Logged per page so the UI can surface "this page degraded". | synthetic test + count of fallback pages on the corpus reported |
| W1.4 | Reindex `v3-hfts`; rerun retrieval + blind sheet. | the 8 hard misses: ≥ 6 flip to hits; single auto ≥ 0.60; `readable@5` ≥ 0.95; no scope regresses vs 08-19 |

If W1.4 misses its bar after one iteration, fall back to approach C for the affected books (per-page), keep W1 for the rest, and re-measure — time-boxed to one more reindex.

### W2 — Parents are sections, payloads are budgeted (≈ 3 days, query-time, no reindex)

The plan (§3.2 E, §3.5) promised section-node parents with a ~6 000-char cap and a `max_context_chars` packer; the ladder shipped 1 000-char chunk parents instead. This is why v2 "wins by returning more text" (its parents stitch up to 4 000 extra chars of the same section), why kraken/dragon (AC at the top of a long stat block, the ability three chunks later) score 0 for both engines, and why cross_page is 0.

| # | change | verify |
|---|---|---|
| W2.1 | `hydrate` returns the **section text** (all chunks of `section_id`, in order, capped ~6 000 chars, centred on the matched chunk when the section exceeds the cap); `text` = section parent, `matched_text` = unit, `chunk_text` kept. | cross_page recall@10 > 0 (closes #375); single / uncued ≥ v2 auto |
| W2.2 | **Budgeted response:** `max_context_chars` on `search`; packer fills results in rank order, truncating the *last* parent to its matched chunk rather than dropping it. Eval reports payload at a fixed 8 000-char budget (the 4B-model column) beside the unbudgeted number, so compactness stays a tracked constraint rather than an accidental chunk size. | payload@8k ≤ 8 000 by construction; MRR unchanged at budget ∞ |
| W2.3 | Dedupe stays by section; add **cross-edition near-dup collapse** (same normalised heading + ≥ 0.9 text similarity across docs → keep best, list others as `also_in`) for the SRD 5.1/5.2.1 twin. | exact_name dup_sections@10 0.667 → < 0.1; no MRR loss |

### W3 — Ranking polish, only after W1/W2 (≈ 1 week)

Numbers before this point are not trustworthy enough to tune on; after W1/W2 they are.

| # | change | verify |
|---|---|---|
| W3.1 | **Rerank bake-off** as a rung: MiniLM-L6 blend (current, weight 0.5 — a "nudge" is the tell that the model isn't trusted) vs `jina-reranker-v1-turbo-en` and `mxbai-rerank-xsmall-v1` (both Apache-2.0 per their model cards, ≤ 80 M params so well inside 500 ms/25 pairs; confirming a clean ONNX export is the rung's first step, as the rerank_latency spike did for MiniLM). Table-aware input: feed linearised `header: cell` rows, not raw pipes. | the 12 rank 1→2 flips recover; uncued ≥ 0.90; latency p50 ≤ 300 ms |
| W3.2 | **Tier calibration (rung 9)** on rerank logit + cosine, calibrated on the *real library* via `library_probe.py`, target ≤ 35 % `strong` ([#366](https://github.com/Unseen-Servant/unseen-legend-lore/issues/366)). | probe distribution; MCP weak-divider inherits |
| W3.3 | Re-run the full blind round (68 q × top-5, readability tick). | κ ≥ 0.74; human single ≥ 0.87; `readable@5` ≥ 0.95 |

### W4 — Cutover (plan Phase 4, unchanged)

API `/v1/`, frontend + MCP migration, `pipeline_version` staleness prompt, side-by-side A/B on identical requests, delete v2. Not started until the W3.3 bar is met.

---

## 5. Definition of done for "v3 replaces v2"

All of the following, on the Phase 0 harness and the real library:

| gate | bar | why |
|---|---|---|
| auto all MRR@5 | ≥ 0.70 (v2 0.701) | parity on the number that has been the target all along |
| auto single MRR@5 | ≥ 0.68 (v2 0.683) | the common path |
| **human** single MRR@5 (blind) | ≥ 0.87 (v2 human) | the metric that inverted the last two verdicts |
| readable@5 (blind) | ≥ 0.95 | the roadblock, graded |
| cross_page recall@10 | > 0 | #375 |
| warm p50 / p95 | ≤ 300 ms / ≤ 1 s | plan §1 goal 1 |
| payload @ 8 000-char budget | ≤ 8 000, top-3 intact | 4B-model consumer |
| golden pages | every page ≥ v2 (per-page, not mean) | §1.4 |
| real-library probe | top-1 correct on all 10; ≤ 35 % strong | the agent-harness finding |

---

## 6. What we will not do

- **Swap the layout model.** The bake-off showed V3/800 px scores the same and costs 4.5× the latency; the failure is detection recall on a distribution no generic layout model was trained on, so a swap trades failure modes. Revisit only if W1 fails its gate.
- **Bloat chunk parents to chase v2's payload.** W2 gives bigger parents *and* a budget; the eval tracks both.
- **Tune ranking on today's index.** Rerank weights, RRF weights and tier thresholds fit to scrambled units will need refitting after W1.
- **Add knobs** (variant expansion, query-shape conditioning) — both already NO-GO on the real-query rule.

---

## 7. Sequence and cost

| week | work | reindexes |
|---|---|---|
| 1 | W0 (harness) + W1.1–1.3 on the 5-min extraction loop | 0 |
| 2 | W1.4 reindex + blind sheet; W2.1–2.3 (query-time) | 1 (+1 contingency) |
| 3 | W3.1–3.2 rungs, W3.3 blind round | 0–1 |
| 4–5 | W4 cutover | 1 (production migration) |

Reindexes are triggered by Jerome, as before. Each rung keeps the one-commit-one-baseline convention; W0 and W1 land as `fix(v3/…)` commits with the corpus-wide extraction report in the message.

---

## 8. Decision log additions

| decision | rationale | reopen if |
|---|---|---|
| Layout model classifies and orders; PyMuPDF blocks carry text | Detection recall 35–50 % on dense TTRPG pages; span-level assignment manufactured the R1 defect | PyMuPDF blocks prove column-wrong on > 5 % of pages (W0.1 will say) |
| Extraction gate = corpus-wide + per-page min | 30-page mean hid a 0.5 and a 100 %-interleaved page three times over | — |
| Section parents + `max_context_chars`, not small parents | the plan's own §3.5 design; small parents were an accident of the ladder | a consumer needs sub-section snippets → serve `matched_text` |
| Readability is graded in the blind round | the roadblock was a readability failure the anchors could not see | — |

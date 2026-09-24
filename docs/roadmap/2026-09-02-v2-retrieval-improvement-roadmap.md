# v2 Retrieval Improvement Roadmap — the pymupdf4llm baseline

**Date:** 2026-09-02
**Status:** approved 2026-09-02 (phase order kept). Phase 0 in progress — see §8 for the `phase0b` re-baseline.
**Decision this builds on:** v2 ingestion (pymupdf4llm → Markdown → heading promotion → structure-aware chunking) stays. The v3 layout-model pipeline is closed as research; `sidecar-v3/` becomes a parts bin whose measured query-side bricks are ported into `sidecar/`.
**Supersedes:** W2–W4 of [2026-08-22-v3-search-recovery-strategy.md](2026-08-22-v3-search-recovery-strategy.md) for the shipping pipeline. The eval harness, the corpus, and the ladder evidence are all kept as-is.
**Objective:** the same one as the rebuild plan — search that is much faster *and* much more relevant than today's v2, for the app UI, Claude, and 4B-class local models — reached by improving what ships, not by replacing it.

---

## 0. TL;DR

- **v2 extraction is good enough to build on.** On the 54-page golden set it scores content 0.992 / order 0.978 / cells 0.953; corpus-wide it has 0 empty pages, label integrity 0.995, block integrity 0.891. Its residual is OSRIC-style two-column interleave (OSRIC 0.816), which stays an open extraction issue ([#329](https://github.com/Unseen-Servant/unseen-legend-lore/issues/329)) and is out of scope here.
- **v2 retrieval loses for three reasons, none of which is the embedding model or the extractor:** (1) the section breadcrumb that feeds both the vector and the reranker is corrupted on most chunks; (2) parents are cut at every sub-heading, so a stat block's answer is split across three results and cross-page questions score 0; (3) ranking is a saturated, two-pass hard reorder whose scores make 66 % of results "strong" and cost 1.2 s per query.
- **The v3 ladder already paid for the fixes.** Heading quality (+0.205 MRR@5), parents that contain the answer (+0.124), system boost after rerank (cued +0.166), blended rerank instead of hard reorder (+0.024 where hard reorder was a wash), dense-leaning hybrid with a stopword-clean lexical query (+0.029 unconditioned). Every one is query-side or metadata-side and ports to v2 without touching extraction.
- **One eval artefact is inflating v2's cued loss:** the v2 eval index carries no game-system tags for 5 of the 7 corpus books, so v2's own soft-boost cannot fire on "osric …", "basic fantasy …", "year zero …" queries. Fixing that is a Phase 0 item and re-baselines the number to beat.
- **Hybrid search ships.** Keyword queries ("goblin AC", "THAC0", homebrew names) are a first-class entry mode and lexical's home turf. v2's 07-09 NO-GO tested the weakest recipe (equal-weight RRF, no stopword handling, in-memory index rebuilt per boot); v3's recipe (dense-leaning weight 0.3, stopword-clean `OR` query, heading-prepended FTS) paid unconditioned on both keyword and natural-language styles. The FTS5 index is built at index time in Phase 1 and fusion is the first ranking rung in Phase 3; the harness sets the weight, not whether it ships.
- **Plan:** measurement first (Phase 0, days), then one batched reindex for heading/section metadata and the persisted FTS5 index (Phase 1), then query-time structure — section parents, budget, drill-in (Phase 2), then ranking on trustworthy metadata — hybrid fusion, boost, blended rerank, tiers (Phase 3), then a blind round and release (Phase 4). A runtime swap to in-process ONNX + sqlite-vec is a separate, gated decision (Phase 5), not a prerequisite.
- **Bar:** auto all MRR@5 ≥ 0.75, human single ≥ 0.90, readable@5 ≥ 0.95, cross_page recall@10 ≥ 0.5, ≤ 35 % `strong` on the real library, warm p50 ≤ 500 ms, top-3 intact inside an 8 000-char budget.

---

## 1. What the evals established

### 1.1 Scoreboard (68 queries, 7 books, anchor-graded)

| | v2 auto (08-15) | v2 **human** (blind) | v3 full stack (08-19) | read |
|---|---|---|---|---|
| all MRR@5 | 0.701 | 0.76 | 0.614 | v2 leads; human grade higher than auto |
| single (book selected) | 0.683 | **0.87** | 0.460 | anchors are too strict on stat blocks/tables (§1.4) |
| cued (query names the system) | 0.519 | 0.51 | 0.592 | v2's weakest scope; partly an eval artefact (§1.5) |
| uncued | 0.942 | 0.94 | 0.825 | saturated |
| cross_page (4 q) | 0.000 | — | 0.000 | structural: parents end at sub-headings |
| dup_sections@10 (uncued) | 0.350 | | 0.200 | SRD 5.1 / 5.2.1 twin |
| payload chars / 25 results | 36 928 | | 21 137 | v2 returns ~1.5 k/result |
| latency p50 / p95 | 1 464 / 1 896 ms | | 244 / 361 ms | rerank is v2's budget |
| κ auto vs human | 0.740 | | not scored | trust the direction, not the third decimal |

### 1.2 What each retrieval brick is worth (the transferable evidence)

The v3 ablation ladder (08-17, on v3's then-scrambled extraction) is the only place each brick was measured in isolation on this harness. Deltas are all-MRR@5 unless noted; every rung was a GO.

| brick | delta | v2 today | port cost |
|---|---|---|---|
| heading-prepended embed text | 0.165 → 0.370 (**+0.205**) | present, but the heading is corrupted on most chunks (§1.5) | index-side fix, one reindex |
| table-row units + coverage guard | +0.040 (table_lookup +72 %) | shipped 2026-07-02 | — |
| parents & dedupe-by-section | +0.124 (dedupe alone is flat; **the win is the parent containing the answer**) | parents stop at any heading change | query-time |
| BM25 fusion, unconditioned, lex weight 0.3, stopword-clean OR query, heading-prepended FTS | +0.029 (keyword +0.048, nl +0.009) | `hybrid` flag default-off after the 07-09 NO-GO, which used equal weight and no stopword strip | query-time re-test |
| system soft-boost as a stable partition, applied *after* rerank | +0.059 all, **cued +0.166**, single/uncued identical | multiplicative ×1.5/×0.7 on saturated scores; cannot fire on untagged books | query-time |
| spell correction | no-op on clean queries (by design) | shipped | — |
| cross-encoder **blended** by RRF (weight 0.5) | +0.024; a hard reorder was a wash (0.617) and wrecked uncued/tables | two-pass hard reorder, ms-marco L-12 | query-time |

### 1.3 Extraction: v2 is the reference, with one known residual

| axis | v2 | note |
|---|---|---|
| golden 54 pages: content / order / cells | 0.992 / 0.978 / 0.953 | 4 of 14 "hard" pages separate backends; v2 loses order on bfrpg (0.850) and yze (0.917) |
| corpus-QA 1 440 pages: block integrity / recall / label / adjacency | 0.891 / 0.998 / 0.995 / 0.970 | 573 pages carry a broken block; **0 empty pages** |
| worst book | OSRIC 0.816 integrity, 275 pages with a broken block | two-column interleave, [#329](https://github.com/Unseen-Servant/unseen-legend-lore/issues/329) |

Read: the text a GM sees is readable and complete; labels ("Armor Class 15 …") survive whole. What is damaged is *metadata* — headings and section boundaries — and that is where the retrieval loss lives.

### 1.4 Where v2 actually loses (per-query diagnosis of its 11 misses)

| queries | what happened | cause | fix |
|---|---|---|---|
| q005/q006 kraken, q041/q042 ancient gold dragon (single, cross_page) | right monster at rank 1–2, but the returned parent is `Kraken > Legendary Actions` or `Ancient Gold Dragon > Actions`; AC lives in the `Kraken` parent, ink cloud in `Actions`. The blind round marked all four **false-MISS**. | heading promotion turns stat-block sub-headings into separate sections; `fetch_parents_extended` stops stitching on any heading change | section parents by path prefix (Phase 2.1) |
| q017 osric falling, q043/q044 5e magic missile, q045 bfrpg magic missile (cued) | rank 1 is an OSRIC chunk whose breadcrumb is the running footer `fOR fRee UpdateS, eRRata …`, scored 0.90–0.99 by the reranker; for q043 the SRD 5.2.1 twin sits at rank 2 | junk breadcrumb in the rerank input (§1.5) + boost cannot fire (no tags, §1.5) + edition twin | Phase 0.1, Phase 1.2, Phase 2.3 |
| q023/q024 yze armor, q050 yze initiative (cued) | YZE `INTRODUCTION` chunks at 0.93–0.99; the answer section is never in the top 5 for either engine | needs a drill-in with the inspector; likely a chunk-boundary or anchor issue rather than ranking | Phase 0.6 |

### 1.5 Metadata damage is in the retrieval path

Measured on the v2 phase0 results (1 700 returned chunks, top-25 × 68):

| defect | share | example |
|---|---|---|
| breadcrumb carries Markdown markup | **84 %** (1 424) | `**Casting Spells** > **Magic Missile**` |
| breadcrumb rooted at OSRIC's running footer | **27 %** (454) | `**fOR fRee UpdateS, eRRata and OtheR OSRIc SUppORt, VISIt:**` |
| breadcrumb rooted at a split word | 11 % (184) | `**S eed** **<u>p</u>** > **Goblin**` (= "Speed") |
| real library (agent-harness probe, 150 results) | 51 % markup, 35 % split letters, `CONTENTS >` roots | `Dexterit y > Grappling` |

The breadcrumb is prepended to the embedding (`_embed_text`) and to the cross-encoder input (`_search_sync`). Half the corpus is embedded and reranked with a corrupted or wrong topical context. This is [#328](https://github.com/Unseen-Servant/unseen-legend-lore/issues/328) + [#367](https://github.com/Unseen-Servant/unseen-legend-lore/issues/367), and it is the single largest lever left.

**Eval artefact:** `evals/engines/v2.py` indexes via `/api/index-files` and never tags game systems; `game_systems.py` knows D&D editions but not OSRIC, Basic Fantasy, Year Zero, Black Hack or Cairn, so those files sit at `unknown` and `_system_boost_factors` is a no-op for 5 of 7 books. v3's rung 6 built its boost map from `SYSTEM_KEYWORDS` in `run_eval.py`. The cued comparison is not apples to apples until v2 gets the same map.

### 1.6 Ranking and score health

- Top-10 tiers on the eval corpus: **66 % strong** (446 / 680), 18 % good, 16 % weak — matching the real-library probe's 62 %. Two YZE `INTRODUCTION` chunks score 0.985 for an initiative query. The sigmoid saturates; tiers carry no information ([#366](https://github.com/Unseen-Servant/unseen-legend-lore/issues/366)).
- Rerank is a hard reorder of the top `rerank_candidates`, then a second straggler pass; the 07-10 ablation found the straggler pass has zero quality effect and that ordering was monotonically better with *less* rerank on the 3-book corpus — yet rerank-off regressed the real library. v3 resolved this tension by blending (RRF, weight 0.5) instead of choosing.
- Boost multiplies scores that already sit at 0.99, so a ×1.5 cannot lift a 0.895 twin over a 0.904 junk chunk.

### 1.7 Latency and payload

p50 1 464 ms. From the 07-10 ablation, rerank-off runs at ~195 ms mean vs ~1 400 ms on, so the L-12 two-pass rerank is ~85 % of the budget. Behind it: Ollama HTTP embedding with a 5-minute unload cliff ([#341](https://github.com/Unseen-Servant/unseen-legend-lore/issues/341)), N+1 parent stitching (`_extend_one` walks rowids one SELECT at a time), settings/manifest JSON re-read up to 5× per request ([#343](https://github.com/Unseen-Servant/unseen-legend-lore/issues/343)), an in-memory BM25 rebuilt per boot. Payload is ~1.5 k chars/result with no budget; the MCP default (15 full parents, ~24 k chars) drowns a 4B model.

### 1.8 Harness limits still standing

- **Single auto understates** (0.68 auto vs 0.87 human): anchors demand the whole answer in one returned text. Section parents (Phase 2.1) fix the cause rather than the anchors.
- **Cued twin:** q043/q044 name "dnd 5e" and require SRD 5.1; SRD 5.2.1 at rank 2 is graded a miss although it is a correct answer. The query set needs an "any of these docs" rule for edition-ambiguous cues.
- **The real-library regime is still ungraded.** The 7-book corpus cannot create hundreds of topically adjacent candidates; `library_probe.py` measures shape (tiers, breadcrumbs) but not correctness. The 2026-08-30 session left the corpus-source question open; §4 Phase 0.4 answers it.
- **Readability was never scored for v2.** The 08-15 blind sheet predates the "garbled" tick; readable@5 is `—` for v2.

---

## 2. Strengths and weaknesses

| | strength | weakness |
|---|---|---|
| **extraction** | readable, complete, column-correct on most pages; tables linearised per row; printed page labels; 0 empty pages; per-page golden gate + corpus-QA in place | OSRIC-class two-column interleave (integrity 0.816); Markdown-as-IR means no bbox, regex cleanup order is load-bearing |
| **chunk metadata** | breadcrumb-prepended embedding is validated (+0.205); TOC + font promotion exists; page spans and labels stored | breadcrumbs carry markup (84 %), split letters, running-footer/CONTENTS roots, stale headings; stat-block sub-headings fragment parents; no `section_id`, no `pipeline_version` read-back |
| **retrieval core** | dense bge-m3 + spell correction + table units + parent dedupe all measured; scoping/collections/filters mature; source_filter honoured | no lexical channel by default (the 07-09 NO-GO tested the weak recipe: 1:1 RRF, no stopword handling, in-memory index rebuilt per boot); boost multiplicative on saturated scores and blind to untagged books; rerank hard two-pass L-12; tiers uninformative; cross_page 0; cross-edition dups |
| **latency / payload** | search off the event loop; atomic staged reindex | p50 1.5 s (rerank), Ollama cold cliffs, N+1 parents, JSON re-reads; no `max_context_chars`; MCP dumps 24 k chars |
| **measurement** | 7-book parallel corpus with hash gate; scope-aware anchors; per-page extraction gate; corpus-QA; blind round with κ 0.74; library probe | single auto too strict; cued twin ambiguity; no graded real-library regime; v2 readability unscored |

---

## 3. Principles

1. **Metadata before ranking.** Rerank weights, fusion weights and tier thresholds fit to corrupted breadcrumbs will need refitting after the heading fix, so the reindex comes before ranking polish (the 08-22 lesson, applied to v2).
2. **One reindex, batched.** Everything index-side (headings, `section_id`, `pipeline_version`, page spans) lands together; Jerome triggers it. Query-time work is measured with `--no-index` in minutes.
3. **A knob must work on real, unlabeled queries** to ship default-on; otherwise it ships as a flag. Hybrid must pay unconditioned.
4. **A harness GO is necessary, not sufficient, for anything the user sees in the list.** Rerank, ordering, dedupe and tier changes are checked on the real library (`library_probe.py` + Jerome's own search) before the default flips; the knob stays.
5. **Gate on the worst scope and the worst page, not the mean.** `--gate` per scope for retrieval, per page for extraction (whose per-page metrics must not regress: this roadmap does not touch the pymupdf4llm call, only promotion and cleanup downstream of it).
6. **One commit, one baseline.** Every rung commits its `evals/baselines/<date>-v2-<rung>.*`.

---

## 4. The roadmap

### Phase 0 — Make the number trustworthy (≈ 3–4 days, no reindex)

| # | change | verify |
|---|---|---|
| 0.1 | **Tag the eval corpus for v2.** `evals/engines/v2.py` sets game systems on indexed files from `run_eval.SYSTEM_KEYWORDS` (via `/api/set-game-systems` + custom systems with keywords, the product's own mechanism), so `_system_boost_factors` sees the same map v3's rung 6 used. Re-baseline v2 as `phase0b` — **this is the new number to beat.** | cued moves (expect ≥ +0.1); single/uncued byte-identical |
| 0.2 | **Breadcrumb QA axis** (`--suite breadcrumb-qa`, no embedding, seconds): per doc, share of chunks whose `section_heading` carries markup, a split letter, a furniture root (running header/footer, `CONTENTS`), or a heading older than N pages with no child; same metrics added to `library_probe.py` for the real library. | baseline committed; the numbers in §1.5 reproduce |
| 0.3 | **Cued-twin rule** in `queries.yaml`: `doc` accepts a list for edition-ambiguous cues (q043/q044: `[srd_5_1, srd_5_2_1]`); the grader's right-file check accepts any listed doc. `verify_anchors` checks all. | q043/q044 re-graded; no other query changes |
| 0.4 | **Local-only library tier.** `evals/retrieval/library.yaml`: ~20 queries authored against Jerome's real library in the confusable regime (spells that exist in 4 books, "falling damage" across systems), each pinned to a PDF SHA-256 + anchors; the harness skips a query whose PDF is absent, so CI is unaffected and no PDF is committed. Resolves the open corpus-source question with the two-tier answer. | tier runs on the local machine; first baseline committed (numbers only) |
| 0.5 | **v2 blind round with the readability tick**, regenerated from the 0.1 baseline. Gives v2's human single and readable@5 — the bar Phase 4 must clear. | κ ≥ 0.74; readable@5 recorded |
| 0.6 | **Drill into the 3 unexplained misses** (q023/q024/q050 YZE) with the HTML inspector; classify as ranking / chunk boundary / anchor and log the verdict. | one paragraph in this doc's decision log |
| 0.7 | `payload@8k` column in the retrieval report (results packed into an 8 000-char budget in rank order) so compactness is tracked from the start. | column present in all later baselines |

### Phase 1 — Index-side foundation (≈ 1.5 weeks, **one reindex**)

Targets [#367](https://github.com/Unseen-Servant/unseen-legend-lore/issues/367), [#328](https://github.com/Unseen-Servant/unseen-legend-lore/issues/328), roadmap items 9 and 15. Extraction output (`_extract_pdf_pages` text) is untouched; only what `promote_headings.py` / `chunker.py` derive from it changes.

| # | change | verify |
|---|---|---|
| 1.1 | **Heading sanitation** before any heading reaches `_embed_text`, the parents store, or the response: strip Markdown emphasis/underline/`<mark>`, rejoin stranded single letters (`S eed p` → `Speed`, `Dexterit y` → `Dexterity`) using the page's own text as the oracle, collapse whitespace, case-normalise small-caps runs (OSRIC `chaRacteR RaceS` → `Character Races`). | breadcrumb-qa: markup 0 %, split 0 % on all 7 books; unit tests per rule |
| 1.2 | **Heading promotion quality:** (a) a heading that `cleanup.py` already classifies as a running header/footer can never become a section root (the OSRIC footer, `CONTENTS`); (b) reject stat-line and caption shapes (`Armor Class 12`, `Table 3-1: …`) as headings — they stay in the body; (c) staleness cap: a heading with no descendant may not cover more than N pages (N derived from the corpus, not asserted); (d) TOC depth-1 pinning stays; (e) sub-modal font levels get distinct levels instead of all → 3. Junk audit rule from v3 Phase 2 (< 2 % junk roots per book) is the acceptance test. | breadcrumb-qa: furniture roots 0 %; junk < 2 % per book; golden extraction gate unchanged (extraction is not touched) |
| 1.3 | **Section identity:** every parent and unit carries `section_id` (hash of doc + heading path + ordinal) and `section_path` (the heading levels joined with a separator — Chroma metadata is scalar-only), persisted in the parents store and in Chroma metadata. This is what lets Phase 2 assemble by hierarchy instead of by heading-string equality. | schema migration test; `section_path` present on 100 % of units |
| 1.4 | **`pipeline_version` read back** ([#15](2026-07-01-retrieval-pipeline-improvement-roadmap.md)/R5): written to the manifest at index time, compared in `/api/index-status`, surfaced as "N files indexed with an older pipeline — re-index" in Library settings. Ships with this reindex so the fix actually reaches indexed libraries. | test: bump version → status reports stale; UI banner |
| 1.5 | Riding the reindex: tighten prose page-spans (heading-sparse runs stamp every chunk with the whole span, `chunker.py:139`). | page spans per chunk ≤ the pages the chunk's text touches |
| 1.6 | **Persisted FTS5 index for hybrid search** (replaces `lexical.py`'s in-memory BM25 rebuilt from a full collection scan on first use, S5). One `unit_fts` table in the parents SQLite (porter, unicode61), written per document inside the same staged/atomic commit as the Chroma upsert, deleted with the source; row text = the *sanitised* breadcrumb + unit text, exactly what the embedder sees (v3 rung 5's precondition). Metadata columns (`source`, `filename`, `game_system`, `parent_id`) so the dense `where` scope applies to the lexical side without a Python filter. | FTS row count = unit count per source after index/delete/rename; scope parity test (a source-filtered FTS query never returns another file); first-search cost after boot ≤ 50 ms (no rebuild) |
| 1.7 | **Reindex the eval corpus; baseline `v2-headings`.** | retrieval: no scope regresses vs phase0b; single and uncued expected up (the v3 ladder's +0.205 was heading quality); extraction gate: no per-page regression (promotion/cleanup output changes; the pymupdf4llm call does not); breadcrumb-qa on the real library after Jerome reindexes: markup ≤ 2 %, furniture roots 0 |

### Phase 2 — Query-time structure (≈ 1 week, no reindex)

Ports W2 of the recovery strategy plus roadmap items 11, 12, 14. Can be developed against the pre-reindex index using heading-string prefix as the interim key; measured after Phase 1.

| # | change | verify |
|---|---|---|
| 2.1 | **Section parents.** `hydrate`/`fetch_parents_extended` assembles by `section_path` prefix: a hit in `Kraken > Actions` returns the `Kraken` section (all sub-sections, document order), capped at ~6 000 chars and centred on the matched unit when the section is longer. One batch query (`WHERE section_id IN (...)`) replaces the rowid walk (S3). `text` = section parent, `matched_text` = the unit that hit (item 11), `chunk_text` kept. Dedupe stays by section. | cross_page recall@10 > 0, target ≥ 0.5 (closes the v2 twin of [#375](https://github.com/Unseen-Servant/unseen-legend-lore/issues/375)); q005/q006/q041/q042 flip; single auto ≥ 0.75 |
| 2.2 | **Budgeted response.** `max_context_chars` on `/api/search` and MCP `search_library`; the packer fills results in rank order and truncates the *last* parent to its matched unit rather than dropping it. MCP default becomes compact (matched snippet + breadcrumb + citation, ~8 k budget) with `get_section(section_id)` and `get_pages(filename, start, end)` for drill-in (item 14). | payload@8k ≤ 8 000 with top-3 intact; MRR unchanged at budget ∞ |
| 2.3 | **Cross-edition near-dup collapse:** same sanitised heading + ≥ 0.9 text similarity across docs → keep the best, list the others as `also_in`. | uncued dup_sections@10 0.35 → < 0.1; no MRR loss (see §8 — the bar is met mechanically by 2.1's dedupe, not this collapse; `dup_titles@10` is the collapse's own metric) |
| 2.4 | **Request-scoped reads:** settings and manifest loaded once per request ([#343](https://github.com/Unseen-Servant/unseen-legend-lore/issues/343)); spell vocab persisted and invalidated by content hash, not chunk count (the FTS side is already persisted by 1.6); Ollama keepalive tuned so the 5-minute unload never lands mid-session ([#341](https://github.com/Unseen-Servant/unseen-legend-lore/issues/341)). | p50 with rerank *off* ≤ 200 ms (07-10 ablation: ~195 ms mean with the N+1 walk still in place); no cold cliff in a 10-minute idle probe |
| 2.5 | Frontend: scroll-to-`matched_text` in the inspector; `also_in` chips; page-label citations already shipped. | manual check |

### Phase 3 — Ranking polish, on trustworthy metadata (≈ 1 week, no reindex)

Numbers before this point are not worth tuning on; after Phase 1 they are. Rungs land in the v3 ladder's order — fusion, then boost, then rerank on top of the fused order — so each baseline isolates one brick.

| # | change | verify |
|---|---|---|
| 3.1 | **Hybrid search: dense + BM25 fusion, default-on.** Query side of 1.6, ported from `sidecar-v3/query/pipeline.py` + `fuse.py`: the lexical query is the content terms of the (spell-corrected) query joined with `OR` after stopword removal (RRF fuses on rank, so a stopword hit would otherwise displace a good dense result — the cause of the 07-09 natural-language regression); both channels take the same scope; weighted RRF, dense 1.0 : lexical *w*, swept over 0.2–0.5 as `--lex-weight` baselines (v3 landed 0.3; 1:1 nicked NL). Hybrid becomes the default of the `hybrid` knob; the knob stays user-visible. Also unblocks the lexical-only regimes dense cannot serve: exact stat codes (`THAC0`, `DC 15`), homebrew/OOV names, and — later, additively — French tokens. | pre-registered, unconditioned: no scope and neither style regresses vs Phase 2 at the chosen weight; keyword MRR@5 up; exact_name recall@5 up; latency ≤ +30 ms. If **no** weight in the sweep clears that bar, the weight ships at the best non-regressing value rather than off, and the finding goes in the decision log |
| 3.2 | **Rerank rebuild.** Runs over the fused order from 3.1. Single pass, pool 25–50, `ms-marco-MiniLM-L-6-v2` int8 ONNX (the asset already staged in `sidecar-v3/models/`; the L-6 NO-GO of 07-10 was as a *hard* reorder). Score is **blended** into the retrieval order by weighted RRF (sweep 0.3–0.7; v3 landed 0.5), never a hard override. Straggler pass deleted. Table units fed as `header: cell` rows, not raw pipes. The `_search_sync` pipeline moves into `sidecar/search/` (pipeline / fuse / boost / rerank / assemble) as it is rewritten — surgical extraction, no other refactor. | MRR@5 ≥ the 3.1 baseline on **every** scope; no new rank 1→2 flips vs 3.1 (per-query diff in the baseline); p50 ≤ 500 ms; **library probe + Jerome's own check before the default flips** (principle 4); rerank knob retained |
| 3.3 | **Boost as a stable partition after rerank** (port `query/boost.py`): sources of a named system move to the front, order within each partition preserved; never a hard filter; production map = the user's tag keyword lists + `game_systems.py` defaults, extended with the five systems the corpus exposed as missing. | cued ≥ 0.65; single/uncued identical |
| 3.4 | **Tier calibration** ([#366](https://github.com/Unseen-Servant/unseen-legend-lore/issues/366)): thresholds fit on the blended score's distribution over the real library (`library_probe.py`), target ≤ 35 % `strong`; the MCP weak divider inherits; one scale whether or not rerank ran. | probe distribution; eval MRR unchanged (tiers don't reorder) |
| 3.5 | Spell-correction tie-break (`thif` → `this`): prefer the library-vocab candidate when its corpus frequency is non-zero. Small, optional. | typo set from `sidecar/evals` re-scored; clean suite byte-identical |

### Phase 4 — Validation and release (≈ 3 days)

- Full blind round (68 q × top-5, readability tick) on the final configuration; library tier (0.4) and library probe rerun.
- CHANGELOG, docs, release tag; the `pipeline_version` banner prompts users to reindex.
- Optional, after release: the answerability smoke ([#369](https://github.com/Unseen-Servant/unseen-legend-lore/issues/369)) — a 4B model over MCP answering ~20 eval questions from the compact payload.

### Phase 5 — Storage and runtime consolidation (decided at the end of Phase 3, not before)

Two independent swaps, both lifted from `sidecar-v3/index/` where they already passed their Phase-1 gates:

- **Store: ChromaDB → sqlite-vec in the parents SQLite.** Licence is *not* the driver (Chroma is Apache-2.0; sqlite-vec is MIT and approved in `third_party/components.json`). The drivers are the rebuild plan's S3/S4/S5 and the constraints this roadmap keeps working around: scalar-only metadata (`section_path` has to be a joined string; secondary system tags need `$in` path clauses), no transaction spanning vectors + parents + manifest (a crash leaves them disagreeing; the orphan-segment GC exists to clean up after it), the 5 461-record write cap, the embedding function coupled to the store, telemetry to opt out of, and ~55 MB of package for a vector index. sqlite-vec cleared the gate the plan set (filtered top-200 over 200 k × 1 024 in **43 ms** p50, recall@200 0.983, native SQL prefilter — `vector_engine_spike`). After Phase 1 the parents SQLite already holds parents, sections and FTS5; vectors are the last table missing from "one file".
- **Runtime: Ollama → in-process fp32 bge-m3 ONNX.** Parity with Ollama vectors verified in `embed_parity_spike`; removes the install prerequisite and the cold-start class of bugs ([#341](https://github.com/Unseen-Servant/unseen-legend-lore/issues/341)).

**Why not now:** Phases 1–3 move relevance and are store-agnostic; swapping the store in the same window would confound every baseline with a storage change. **Why it costs users nothing later:** Chroma exposes stored embeddings (`collection.get(include=["embeddings"])`), so the store swap is a one-shot *migration* of existing vectors into sqlite-vec — no re-embed, no reindex — and the runtime swap is invisible (same model, same vectors). Both are measured on the harness like any rung: MRR byte-identical (same vectors), p50 and package size are the numbers.

**Decision rule at the end of Phase 3:** do the store swap if any of (a) p50 > 500 ms, (b) a Phase 2/3 item had to work around Chroma metadata or transaction limits in a way that shipped as user-visible behaviour, (c) the packaged-app size or first-launch story is the next complaint. Do the runtime swap if Ollama onboarding or cold cliffs are the top support issue. Either can go alone.

---

## 5. Definition of done

| gate | bar | why |
|---|---|---|
| auto all MRR@5 | ≥ 0.82 (sections 0.862; headings 0.790) | the ladder's bricks are worth more than this on a clean base |
| auto single MRR@5 | ≥ 0.82 (sections 0.948) | section parents fix the four stat-block "misses" |
| auto cued MRR@5 | ≥ 0.72 (sections 0.722) | boost-after-rerank + clean breadcrumbs; v3 reached 0.675 on scrambled extraction |
| keyword-style MRR@5 | ≥ nl-style + 0.03, and ≥ 0.85 (phase0b 0.810 / nl 0.722) | hybrid is default-on; lexical must show up where it is supposed to |
| **human** single MRR@5 (blind) | ≥ 0.90 (sections 0.906 by label transfer, 92 % covered; headings 0.88 scored 2026-09-23; phase0b 0.87) | the metric that inverted two verdicts |
| readable@5 (blind) | ≥ 0.98 (sections 0.971 by label transfer; headings 0.962: 13 garbled chunks, same torn-table shapes as phase0b's 12; phase0b 0.965) | scored for v2 on 2026-09-09; the bar sits above the base so Phase 1/2 must not tear tables further |
| cross_page MRR@5 | ≥ 0.75 (sections 1.000; headings 0.354) | section parents put the whole stat block in one result |
| dup_sections@10, uncued | < 0.1 (sections 0.200; see §8 — met mechanically by 2.1's dedupe; dup_titles@10 1.350 reported) | edition twin |
| warm p50 / p95 | ≤ 500 ms / ≤ 1 s (sections 1 126 / 1 474 with rerank; 76 ms rerank-off) | single-pass blended rerank + no N+1 |
| payload @ 8 000-char budget | ≤ 8 000, top-3 intact (sections-8k: payload 6457, top3_fit@8k 1.000, MRR@5 at budget 0.854 vs 0.862 unbudgeted) | 4B-model consumer |
| breadcrumb QA, real library | markup ≤ 2 %, furniture roots 0, split letters 0; eval corpus 2026-09-11: markup 0, mixed_case 0, split ≤ 1 %, furniture ≤ 1 % on all 7 books; real library pending reindex | #367 / #328 |
| tiers, real library | ≤ 35 % `strong` | #366 |
| golden extraction gate | no per-page regression vs 2026-08-31-v2-extraction (promotion/cleanup output changes; the pymupdf4llm call does not) | the extraction adapter grades post-promotion text |
| library tier + probe | top-1 correct on all queries; no regression vs its first baseline | the confusable regime |


*Bars re-set 2026-09-02 after `phase0b`: the original bars were written against the untagged 08-15 baseline, and the corrected base already cleared three of them (all ≥ 0.75, keyword ≥ 0.78, cross_page recall@10 ≥ 0.5). The new values are proposed, not yet confirmed by Jerome.*

---

## 6. What we will not do

- **Touch extraction.** pymupdf4llm, `cleanup.py`, table linearisation stay as they are; OSRIC-class two-column interleave ([#329](https://github.com/Unseen-Servant/unseen-legend-lore/issues/329)) stays open and is a separate decision (candidates when it reopens: pymupdf4llm block ordering options, or v3's native-block builder `ingest/blocks.py` applied under v2 — both are extraction-track work with their own gate).
- **Swap the embedding model or the layout model.** Neither is the gap.
- **Add knobs already NO-GO on the real-query rule:** variant expansion, query-shape conditioning, LLM captioning, centroid parents.
- **Rewrite `server.py` wholesale.** Only the search pipeline is extracted, because it is being rewritten anyway (3.1).
- **French.** Deprioritised 2026-08-30; `lang` fields and the ASCII rerank guard stay.

---

## 7. Sequence and cost

| week | work | reindex (eval corpus) | reindex (Jerome's library) |
|---|---|---|---|
| 1 | Phase 0 (0.1–0.7), Phase 1.1–1.5 on unit tests + breadcrumb-qa | 1 (0.1 re-baseline) | 0 |
| 2 | Phase 1.6 reindex + baseline; Phase 2.1–2.3 built on the interim key | 1 (+1 contingency) | 1 (to run breadcrumb-qa / probe) |
| 3 | Phase 2.4–2.5; Phase 3.1 hybrid sweep, 3.2 rerank | 0 | 0 |
| 4 | Phase 3.3–3.5; Phase 4 blind round | 0 | 0 |
| 5 | release; Phase 5 decision (store / runtime swaps are vector migrations, not reindexes) | 0 | 1 (users, via the banner) |

Reindexes are triggered by Jerome, as before. Each rung is one commit with its baseline; Phase 1 lands as `feat(sidecar/headings)` commits carrying the breadcrumb-qa report in the message.

---

## 8. Decision log additions

| decision | rationale | reopen if |
|---|---|---|
| v2 ingestion is the base; v3 is a parts bin | v2 extraction 0.992/0.978/0.953 and 0 empty pages; the retrieval loss is metadata + assembly + ranking, all portable | an extraction defect (not #329) shows up in the blind round's garbled ticks |
| Reindex once, before ranking polish | fusion/rerank/tier fits on corrupted breadcrumbs would need refitting | — |
| Section parents by `section_path` prefix, capped, centred | the four single "misses" are one section split in three; cross_page is 0 for the same reason | a consumer needs sub-section snippets → `matched_text` already serves it |
| Blended rerank (RRF nudge), L-6 int8, single pass | hard reorder was a wash on v3 and monotonically harmful on v2's 07-10 ablation; rerank-off regressed the real library — blending keeps both signals | library probe or Jerome's check says otherwise → weight → 0 keeps retrieval order |
| `2026-09-02-v2-phase0b` is the v2 number to beat (replaces 08-15 `phase0`) | same pipeline; the harness now tags the corpus, accepts SRD edition twins for "dnd 5e" cues, and reports `top3_fit@8k` — cued 0.519 → **0.632**, all 0.701 → **0.766**, single 0.683 → 0.753, uncued 0.942 unchanged. Per-query vs 08-15: six cued moves (tags + twins) and four single cross_page flips (kraken/dragon MISS → rank 2–3) that come from the 08-29 grader change b31fd50 (evidence-set grading), not from Phase 0 code — cross_page 0.000 → 0.417 for the same reason. Remaining misses: q017, q023, q024, q050 (all cued; three are the Task 8 drill). p50 1 274 ms. | — |
| `2026-09-02-v2-phase0b` blind round scored 2026-09-09 (κ 0.735, 68/68 reviewed) | human vs auto per scope: cued 0.54/0.63 (auto over-grades: anchors accept the twin-system chunk the human rejects), single 0.87/0.75 (auto under-grades: stat blocks split in three), uncued 0.94/0.94. readable@5 0.965; every one of the 12 garbled ticks is a table torn mid-row or a prose lead-in cut from its table (Black Hack CONVERTING SAVES ×3, SRD armor table ×2, OSRIC ×3, Cairn ×2, gold dragon ×2) — a chunking flaw, not an extraction one, so the v2-base decision above stands. 42 disagreements logged in `evals/baselines/2026-09-02-v2-phase0b.blind.md`; cued false-hits are the anchor-side work for Phase 3. | κ drops below 0.70 on a later round |
| Hybrid search ships default-on, with v3's recipe; the harness sets the weight | keyword queries are a first-class entry mode; the 07-09 NO-GO tested the weakest recipe (1:1, no stopword strip, per-boot in-memory index); v3's unconditioned recipe paid on both styles (+0.029 all, keyword +0.048) | the sweep finds no non-regressing weight → ship the best one and record it; query-shape conditioning stays rejected (real-query rule) |
| Two-tier eval corpus (committed CC + local-only library tier) | the confusable regime cannot be committed; anchors + PDF hashes can | — |
| Store (Chroma → sqlite-vec) and runtime (Ollama → ONNX) swaps are Phase 5, decided at the end of Phase 3 | the bricks that move relevance are store- and runtime-agnostic; swapping mid-ladder confounds baselines; both swaps are vector migrations, not reindexes, so deferring costs users nothing; Chroma's licence (Apache-2.0) is not a driver, its metadata/transaction limits and footprint are | p50 > 500 ms, a Chroma limitation leaks into shipped behaviour, package size/first launch becomes the complaint, or Ollama onboarding pain |
| Phase 1 landed 2026-09-12 (commits bfcf2c1..15a9f74 + fix wave) | heading sanitation + promotion quality landed and the eval corpus was reindexed; breadcrumb-qa 2026-09-02 → 2026-09-11: markup 0.903 → 0, mixed_case 0.258 → 0, split_letter 0.317 → ≤ 0.010 (srd_5_1 13, srd_5_2_1 7, osric_2e 28, others 0; residue is legitimate single-letter words, spell components, OSRIC drop-caps), furniture_root 0.239 → ≤ 0.009 (osric_2e 23/2671 its own contents pages, bfrpg 3, yze 2, others 0; OSRIC's 2664/2706 footer root gone) — every book's top root is now a chapter title; retrieval `2026-09-12-v2-headings` vs `2026-09-02-v2-phase0b`: all MRR@5 0.766 → 0.790, single 0.753 → 0.767, cued 0.632 → 0.701, uncued 0.942 → 0.925, cross_page 0.417 → 0.354, recall@3 all 0.868 → 0.868, p50 1 274 → 1 094 ms, top3_fit@8k 0.838; gate FAILED on two rows (single recall@3 0.875 → 0.833, q041 rank 3 → 4, sibling dragon stat blocks; uncued mrr@5 0.942 → 0.925, q063 rank 1 → 2, OSRIC's now-clean `CHAPTER VI: TREASURE > MAGIC SWORDS` edges the 5.2.1 weapons table) against 10 per-query improvements and 5 one-rank regressions, inside a measured ≈ 0.01–0.02 run-to-run noise floor (two reruns of identical code scored all 0.798 and 0.790); controller ruling: **ACCEPTED** as the Phase 1 reference — the failing rows are single-query moves at the noise floor whose causes are Phase 2 (section parents) and Phase 3 (hybrid) work, and the gate stays fail-closed for ranking rungs; blind round on `2026-09-12-v2-headings` scored 2026-09-23 (68/68): κ 0.743 (cued 0.853 / single 0.620 / uncued 0.638), human vs auto MRR@5 all 0.80/0.79, single 0.88/0.77 (auto still under-grades split stat blocks — fixed by Phase 2 sections), cued 0.62/0.70 (auto over-grades twin-system chunks); readable@5 0.962 (13 garbled: torn pipe tables, an index page, a lead-in cut from its table) — one chunk under phase0b's 0.965, i.e. Phase 1 tore no new tables | the real-library probe shows furniture roots |
| Heading oracle = the page's own spans; no staleness cap; count-based breadcrumb gate | 2026-09-09 probe: the page's own text is a reliable oracle for rejoining split headings, so no TOC/vocabulary fallback was needed; heading-span measurement: p99 = 2 pages, max 16 — the tail is legitimate 4–5-page leaf sections, not staleness, so no cap was built; breadcrumb-qa's regression gate compares per-doc flaw counts, not rates, because denominators move when sections merge or split across a heading change; the junk-shape rule (titles with ≥ 2 numbers or > 80 chars) has known false positives but caused no corpus damage in Phase 1 — watch `junk=` in the `[promote]` log on the real library | a book's spans are themselves scrambled (then a TOC/vocabulary fallback is the next rule), or a childless heading > 10 pages appears on the real library |
| Phase 2 landed 2026-09-12 (commits 045a4c4..b1dd374) | Query-time structure shipped, no reindex: sections assembled by `section_path` prefix (shallowest fitting ancestor, `SECTION_CAP` 6000), a `max_context_chars` budget packer, MCP compact `search_library` (n_results 8) plus `get_section`/`get_pages` drill-in, cross-edition near-dup collapse with `also_in`, request-scoped settings/manifest reads + persisted spell vocabulary + boot warm-up (#343, #341), and UI matched-passage highlight/scroll + GFM tables + `also_in` chips + page labels. `2026-09-12-v2-sections` vs `2026-09-12-v2-headings`, gate **PASSED** (8 queries better, 0 worse): all MRR@5 0.790 → 0.862, single 0.767 → 0.948, cued 0.701 → 0.722, uncued 0.925 unchanged; recall@3 all 0.868 → 0.912; cross_page MRR@5 0.354 → 1.000 and recall@10 1.0 (q005/q006/q041/q042 flip — the kraken and gold dragon stat blocks now come back whole, closing the v2 twin of #375); dup_sections@10 uncued 0.400 → 0.200, all 0.235 → 0.132; new `dup_titles@10` (reported, not gated) uncued 1.350, all 0.456; payload_chars all 37 294 → 44 203; top3_fit@8k all 0.838 → 0.750; warm p50 1 094 → 1 126 ms with rerank on, 76 ms rerank-off (mean 84, p95 118); idle probe 1.07× after 600 s (1 183 → 1 261 ms); section-assembly store time 27.7 → 2.6 ms on a synthetic 3 MB book after the per-request memo. `sections-8k`: payload 6 457, top3_fit@8k 1.0, MRR@5 0.854 at budget. Human bars by **label transfer** (`evals/blind/transfer.py`, 2026-09-23): the 68-query headings labels carried onto the sections results by structural containment (same book, section heading path is a prefix of the chunk breadcrumb, section span covers the chunk span), 92 % of the top-5 covered, lower and upper bounds agree — human single MRR@5 **0.906** (auto 0.948; bar 0.87 met), human all 0.81 (auto 0.86), cued 0.64 (auto 0.72 — auto still over-grades twin-system chunks), readable@5 **0.971** (10 garbled: the torn tables now inside their sections). No separate sections sheet was scored. | the sections blind round's readable@5 < 0.965 or human single < 0.87, or the real-library probe shows over-wide sections |
| `dup_sections@10` retired as the 2.3 gate; `dup_titles@10` reported | `dup_sections@10` keys on (file, full breadcrumb) and is driven to ~0 mechanically by dedupe-by-section (two results cannot share a root) — 2.3's bar is met by 2.1, not by the collapse; `dup_titles@10` is reported in `COST_METRICS`, not gated, and measures post-collapse residue (a 1.35 on uncued means same-titled sections across books whose text is genuinely different, e.g. Goblin in OSRIC vs SRD — correctly kept) | — |
| Sections = shallowest fitting ancestor under `SECTION_CAP` 6000; labels blank on widened spans; table hits highlight the parent block | `SECTION_CAP = 6000` in `sidecar/parents_store.py` is the width knob; `section_root_for` picks the shallowest ancestor whose subtree fits, so a short chapter is returned whole; `windowed` marks cut results; a single result can exceed the cap when its matched parent alone is larger. Printed page labels are blanked whenever the returned span is wider than the matched unit's pages (blank = "cite the physical span" for MCP `_page_span` and the app's `pageCitation`); a parents label column is the Phase 3 candidate that restores them. Table hits highlight their whole parent block, not one row (the embed unit is the linearised row sentence, never a substring of the pipe markup; `findMatchedRange` falls to the `chunk_text` tier) — the highlight wash is masked by the table background, only the left border shows | a consumer needs sub-row highlighting → the row-level embed unit is the fix, not the highlighter |
| `/api/search` may return fewer than `n_results`; `exhausted` flag | Dedupe-by-section, near-dup collapse, and the budget packer can each shrink the pool below `n_results`; the response's `exhausted` flag tells the app when the overfetch pool ran out before enough distinct sections were picked; the app's `reachedEnd` now reads it | — |
| MCP defaults: compact search, `n_results` 8, `get_section`/`get_pages` | `search_library` defaults changed: `n_results` 15 → 8, compact output (600-char matched snippet + `Full section: get_section("id")` pointer, no server budget in compact mode; `full_text=True` restores whole sections under an 8 000-char budget); new tools `get_section(section_id)` (resolves container ids by path segment; reports `windowed`) and `get_pages(filename, start, end)` (1-based, ≤ 20 pages, 404 past the last page) | — |
| #343 / #341 closed by 2.4 | Request-scoped settings/manifest reads, spell vocabulary built from `unit_fts` and keyed on a manifest content digest (full FTS coverage picks the store scan over the Chroma scan, so a partially re-indexed library keeps the Chroma path), boot warm-up and the 120 s keepalive together address #343 and #341; both issues can be closed. Warm p50 with rerank on is 1 126 ms against the ≤ 500 ms bar — rerank is the remaining cost, and Phase 3's single-pass blended rerank is the lever | a regression reopens either request-scoped reads or the keepalive |
| 3.1 + 3.3 landed 2026-09-23 (commits 4d5b52f, 416455f — the latter pushed under a copy of 4d5b52f's message; `main` refuses force-pushes, so this row is its description) | **Hybrid:** the 0.2–0.5 RRF weight sweep moved nothing because weighted RRF at k=60 ranks a BM25-only #1 at w=0.3 like dense #143 — zero BM25-only units reached the top-50 rerank pool on all 68 queries, though BM25 alone had rel@1 on 14 queries vs dense 12 and rescued q007/q017/q018/q057. The fix is pool admission, not weight: the rerank pool is the head of the order ∪ the BM25 top-M (`LEXICAL_RERANK_POOL` 10; M=20/30 identical, +~11 ms p50 per extra pair). Query side: stopwords stripped, unicode tokens kept whole ("écran"), weighted `rrf_fuse`, `lex_weight`/`lex_pool` eval knobs, `where_to_sql` degenerate shapes guarded. **Boost:** stable partition of the named system's sources, before rerank (fills the pool) and after it (incl. the straggler re-sort); the ×1.5/×0.7 multipliers lost to saturated cross-encoder scores (q048: 5e "Surprise" 0.92×0.7 > OSRIC 0.39×1.5). Defaults gain YZE, Black Hack, Cairn. Fresh baselines, gate vs sections passed on both: `2026-09-23-v2-boost` all 0.864 / cued 0.729 / single 0.948 / uncued 0.925, keyword 0.882 / nl 0.846, p50 1 139 ms (q022 #3→#1, 0 losses); `2026-09-23-v2-hybrid` all **0.879** / cued **0.771** / single 0.948 / uncued 0.925, keyword **0.912** / nl 0.846, recall@5 0.941, p50 1 265 ms (+q017 MISS→#1, 0 losses). Hybrid stays default-off until 3.2 brings p50 inside the +30 ms latency bar (it is +126 ms); flipping it needs a migration for saved `search_settings.json` files that pin `hybrid: false`. | a real-library query set shows BM25-admitted candidates crowding out dense answers, or the boost partition hides a legitimately-elsewhere answer below a page of named-system noise |
| 3.2 landed 2026-09-24 (commit 8b00088); hybrid default-on | **Rerank:** int8 `ms-marco-MiniLM-L-6-v2` (Xenova `onnx/model_quantized.onnx`, a fastembed custom model in its own cache dir) replaces L-12 fp32 — 222 vs 981 ms per 60 real pairs. **Hard reorder kept; the blend is rejected on v2:** weighted-RRF blending of the cross-encoder order into the pool's retrieval order lost on every weight 0.3–1.0 (cued 0.66–0.71 vs 0.771), because the BM25 extras sit at the pool's tail and the blend pinned them down (q017 → #11). This reverses the §8 "blended rerank" row for v2 — v3's blend result came from a different retrieval order. L-12 int8 measured 643 ms p50, no better. The straggler pass stays, scoring-only (#306 single scale, no re-sort). Table units were already linearized `header: cell` rows. `2026-09-24-v2-rerank` (hybrid on, fresh index) vs `2026-09-23-v2-hybrid`: all 0.879 → **0.884**, cued 0.771 → 0.771, single 0.948 → 0.948, uncued 0.925 → **0.942**, keyword 0.912 → **0.926**; warm p50 1 265 → **358 ms** (p95 443) — the ≤ 500 ms bar is met. The reused-index run showed cued 0.750 (q017/q020 #1→#2); the fresh run recovers q019 #2→#1, inside the known fresh-run noise. Jerome checked it in the app on the real library before landing. **Hybrid default-on**: `search_settings.json` gains `version: 2`; v1 files wrote every field, so their `hybrid: false` is dropped on load; the UI toggle leaves the Experimental group. | the real-library probe or Jerome's use shows L-6 ordering worse than L-12 on dense libraries (`RERANK_MODEL=Xenova/ms-marco-MiniLM-L-12-v2` restores it without a code change) |

# Retrieval Pipeline Improvement Roadmap

**Date:** 2026-07-01
**Scope:** End-to-end retrieval accuracy and search UX — ingestion → chunking → embedding → query → rank → UI/MCP.
**Method:** Multi-agent audit of the full pipeline, each finding adversarially code-verified, plus a **live probe against the real index** (6 docs / 13,833 chunks: Dragonbane, OSRIC, 5e SRD, Wight-Box) and a scan of the sibling `unseen-legend-lore-experiments` spikes. 35 findings survived verification; 4 were refuted and dropped (see appendix).

Priority = (impact × frequency × confidence) ÷ effort, with a bias toward **things that are silently wrong or broken right now**. Effort: **S** ≈ hours, **M** ≈ a day or two, **L** ≈ multi-day.

---

## 0. Two things are broken right now (live-reproduced)

These were found empirically by running the real sidecar against production data — not visible from a static read.

### 0.1 — The MCP search path times out in production
`SidecarClient` in [mcp_server.py](../../sidecar/mcp_server.py) uses `httpx.AsyncClient()` with the **default 5s timeout** and catches only `ConnectError`/`HTTPStatusError`. Warm reranked searches take **5–7s**, so `search_library` dies with an unhandled `TimeoutException` — reproduced twice while the sidecar logged `200 OK`. The flagship "ask Claude mid-session" feature fails for typical queries; a fresh install's *first* MCP search always fails (cold-start reranker download + 5s ceiling).
**Fix:** explicit generous timeout + catch `TimeoutException` and surface a real message. **Effort: S. Highest-leverage fix in this document.**

### 0.2 — The reranker inverts French queries and displays `0.0` relevance
The default `Xenova/ms-marco-MiniLM-L-12-v2` cross-encoder ([reranker.py](../../sidecar/reranker.py)) is English-only. On `comment fonctionnent les dégâts de chute`, rerank-**on** put "Underwater Combat" at #1 with every result at 0.0; rerank-**off** returned the two correct FALLING sections at #1/#2. It is also the **entire latency budget** (0.2–0.8s off vs 1.4–7.1s on) and **was never validated against the eval harness** — while the only reranker experiment on record (`hybrid_retrieval_spike`) was a **no-go** (−0.232 MRR@5) on a *stronger* model with the same failure modes (512-token truncation, English calibration).
**Fix:** validate against the harness; interim, skip rerank for non-English queries or expose the existing `rerank` flag (cosine-fallback is already a tested path). **Effort: S–M.**

---

## Tier 1 — Broken or silently wrong, small fix, hits everyone

| # | Opportunity | Evidence | Effort | Issue |
|---|---|---|---|---|
| 1 | Fix the MCP timeout (§0.1) | `mcp_server.py` `SidecarClient` | S | [#304](https://github.com/Unseen-Servant/unseen-legend-lore/issues/304) |
| 2 | Reranker safety: validate + skip/flag for non-English (§0.2) | `reranker.py`, `server.py:2980` | S–M | [#305](https://github.com/Unseen-Servant/unseen-legend-lore/issues/305) |
| 3 | **Reconcile the relevance score.** Three scales — rerank sigmoid, `1−cosine`, and saturated 0.999s — flow through one `relevance` field to UI *and* Claude, producing non-monotonic "% match". Drop the raw % or tag which results were reranked. | `server.py:2994`, `SearchResults.svelte` | S | [#306](https://github.com/Unseen-Servant/unseen-legend-lore/issues/306) |
| 4 | **Muting one system silently drops ALL untagged files** from search. Homebrew, indie, and French books auto-tag as `unknown`; muting e.g. "Pathfinder 2e" removes every untagged book. Add `unknown` to the include-list + an "Untagged" filter row. | `+page.svelte:319`, `FilterMenu.svelte` | S | [#307](https://github.com/Unseen-Servant/unseen-legend-lore/issues/307) |
| 5 | **Collection scoping filters by filename, not path.** Same-named books (`/5e/Monster Manual.pdf` vs `/pf2e/…`) leak across systems in scoped / active-context search. Switch the where-clause to the `source` path (already stored per chunk). | `server.py:2911` | S | [#308](https://github.com/Unseen-Servant/unseen-legend-lore/issues/308) |
| 6 | **Filter mismatches fail silently on MCP.** `game_system='Pathfinder'` (tag is `'Pathfinder 2E'`) → zero hits → Claude reports the content isn't in the library. Validate/fuzzy-resolve against the manifest and surface the reason (server already returns a `message` that the MCP formatter drops). | `mcp_server.py:284`, `server.py:2914` | S | [#309](https://github.com/Unseen-Servant/unseen-legend-lore/issues/309) |
| 7 | **No relevance floor.** Searching a 5e spell scoped to a Pathfinder collection confidently returns 15 wrong-system hits (dense NN always finds *something*). Add a weak-match divider using the reranker's `[0,1]` score. | `server.py:2957` | S | [#310](https://github.com/Unseen-Servant/unseen-legend-lore/issues/310) |

---

## Tier 2 — Highest accuracy leverage (evidence-backed)

### 8 — Ship table row-linearization *(largest unadopted win)*
`table_retrieval_spike` measured **+0.152 MRR@5** on table queries with **reference code ready to copy** (`linearize_tables.py`), zero LLM cost, embed-side only (re-index, no schema/retrieval change). It also resolves two other confirmed findings:
- Large tables embed as a **single diluted vector** ([granularity.py:196](../../sidecar/granularity.py)) — a query for one row loses to prose that merely mentions the term.
- **Silent ~2048-token embedding truncation** — verified live, the effective Ollama context is ~2048 (not the documented 8192), so big tables have their tail unsearchable regardless of query.

Targets the signature live-play lookup ("what's on roll 96–00"). **Effort: M. Do this as its own focused piece — it's the reason the tool exists.**

### 9 — Fix heading-promotion quality
Live probe showed **junk breadcrumbs actively outranking real content**: a stale never-closed "Level 5 Cleric Spells" heading covers most of Wight-Box and its parents beat OSRIC's real wandering-monster tables at 0.999; OSRIC roots everything at "**CONTENTS**"; stat-lines and table captions get promoted as headings. Breadcrumbs are prepended to **both the embedding and the rerank input** ([server.py:712](../../sidecar/server.py:712)), so bad headings poison ranking, not just display. Reject stat-line/caption headings, cap heading staleness, add the flagged **R4** running-header strip, assign distinct sub-modal heading levels (not all → level 3), and synthesize headings for bold body-size entry names. [promote_headings.py](../../sidecar/promote_headings.py). **Effort: M.**

### 10 — Two-column reading-order in extraction
The Dragonbane FALLING rule comes back with sentences interleaved out of order — **the rule as displayed is factually wrong, with a correct citation attached.** Most dangerous class here: confidently-wrong at the table. Per-page extraction at [server.py:298](../../sidecar/server.py:298). **Effort: M.**

---

## Tier 3 — Last-mile result UX

| # | Opportunity | Evidence | Effort |
|---|---|---|---|
| 11 | **Return + highlight the matched child span.** Every result's snippet shows the *parent's first line* (grappling hit → snippet shows initiative text); the inspector renders up to 6,000 un-highlighted chars. The matched unit already exists server-side — return it as `matched_text` and scroll-to-match. | `server.py:3038`, `SearchResults.svelte`, `SearchInspector.svelte` | M |
| 12 | **Stitch stat-block sub-sections across the breadcrumb hierarchy.** "Solar stat block" returns AC/HP but not Actions/Legendary Actions (separate parents that never merge). ~5-line prefix-match change. | `parents_store.py:147` | S |
| 13 | **Open-at-page is a no-op on macOS Preview** (`#page=N` ignored, issue #113). Render the page to PNG in-app via the shipped PyMuPDF, or surface the page number at open time. | `pdfUrl.ts`, `+page.svelte:433` | M |

---

## Tier 4 — MCP surface & durability

| # | Opportunity | Evidence | Effort |
|---|---|---|---|
| 14 | **Add a `get_pages(filename, start, end)` MCP tool.** Claude can't drill into a hit; multi-page tables/sections are unreachable (stitch budget is 4000 chars). Also trim the verbose `n_results=15` full-parent default (~24k chars/call). | `mcp_server.py`, `parents_store.py` | S–M |
| 15 | **Pipeline-version staleness signal.** `chunker_version`/`embedding_model` are written but **never read back** — every fix in this doc silently never reaches an already-indexed library. Add a `pipeline_version` to the manifest, compare it in `/api/index-status`, surface "N files indexed with an older pipeline." | `server.py:696`, `server.py:1194`, `LibrarySettings.svelte` | S–M |
| 16 | **Wire the eval harness into the production repo as a regression gate**, and **add ~15 French queries** (currently *zero* multilingual eval despite it being the #1 confirmed failure mode). This is the meta-enabler for validating items 2, 8, 9 with data instead of vibes. | experiments repo `queries.yaml`, `score_retrieval.py` | M |

---

## Quick wins worth batching

- **Game-system soft-boost** — `hybrid_retrieval_spike` measured **+0.042 cross-system MRR**, ~30 lines, "never hurts"; blocked only on a `KNOWN_SYSTEMS` keyword gap (`game_systems.py`).
- **Printed page-labels in citations** — surface `doc[i].get_label()` so "p.167" matches the book's printed page, not the physical index.
- **Debounce min-query-length** — the full embed+rerank pipeline fires per keystroke-pause on 1-char queries ([Header.svelte](../../src/lib/Header.svelte)).
- **Tighten prose page-spans** — heading-sparse sections stamp every chunk with the whole run's span, so "pp.33–41" is a 9-page scan ([chunker.py:139](../../sidecar/chunker.py:139)).
- **Zero-result recovery** — "Search entire library instead" affordance + surface the backend `message` (both currently dropped).

---

## Explicitly ruled out — don't spend time here

These were tested and rejected by the project's own spikes; don't re-propose:

- **VLM / GLM-OCR extraction** — `glm_ocr_spike` NO-GO (drops table columns; ~20s/page).
- **Centroid parent vectors** — `chunk_granularity_spike` NO-GO (table recall regresses 0.800 → 0.600).
- **LLM table captioning** — `table_retrieval_spike` NO-GO (strict subset of linearization's wins at high cost).
- **Extractor swap to Marker/Docling** — pending the in-progress `marker_docling_spike` *and* conflicts with the ONNX-not-PyTorch constraint. Don't pre-empt it.

### ⚠️ REOPEN (do not treat as closed) — BM25 / lexical hybrid search

**Verdict: reopen-with-caveats.** A dedicated adversarial re-validation (three evidence readers → a two-sided juror panel → neutral chair) re-derived the scorer from `score_retrieval.py` and recomputed every headline from `outputs/retrieval.full.raw.json`. **Both jurors — including the one assigned to defend the rejection — concluded the prior NO-GO does not settle the question for this library.** Expected value of a proper re-test: **high**.

**What the spike genuinely established (and reproduces exactly):** untuned uniform-RRF plain-BM25 fused into an already-strong heading-dense baseline is a wash-to-slight-loss *on that corpus*. V0_h MRR@5 = 0.851, V2_h = 0.723 (Δ −0.128) reproduce to the digit; bge-m3 native sparse (V3 = 0.550) failed the same way; and on this corpus BM25 added **zero** complementary top-5 recall (0 unique answers found vs 10 the other way). That narrow finding is real — **the reopen case rests on generalization, not on latent BM25 wins hiding in this data.**

**Why it does *not* generalize to your library:**
- **The loss is non-uniform and inverts the verdict's own thesis.** Recomputed per-category, V2_h − V0_h is **stat_block +0.083** (fusion hits a perfect 1.000) while table −0.197, cross_page −0.167, cross_system −0.155, prose −0.147. The one category BM25 *helped* is exact-proper-noun lookups — the GM's single most common query type. The "heading-prepend already provides the proper-noun signal" claim (`FINDINGS.md:110`) is **asserted, never ablated**, and confounded (V0_h stat_block recall was pre-saturated at 1.000, leaving RRF zero headroom).
- **The metric can't see BM25's edge.** 23/40 queries have answer windows ≥20 pages (owlbear 151pp; fireball/bless/red-dragon 101pp each), so page-overlap MRR@5 scores a precise exact chunk and a neighboring wide chunk identically. Exact-chunk precision — BM25's whole point — was unmeasurable. The authors deferred the manual deduped scoresheet they themselves call the real discriminator.
- **The fusion ran in its weakest possible config.** Pure `1/(k+rank)` at fixed k=60, equal 1:1 weight, and `_variant_v2_h` fused heading-dense with **plain** BM25 — the BM25 side never got the heading signal. A heading-prepended BM25 index (V4) was *built* (`build_bm25.py:96`) but never fused; V3_h was defined (`run_retrieval.py:141`) but never run.
- **It's inside the harness's own noise.** The ground-truth fix in the same spike swung V0_h by **+0.228 MRR** — larger than the −0.128 being treated as decisive.
- **Zero multilingual coverage.** The corpus is 3 English PDFs / 40 English queries (0 non-ASCII), with an **English-only tokenizer** (`porter … remove_diacritics 1`, `build_bm25.py:60`) that mis-stems French and folds accents so distinct French tokens collide. Your library is mixed FR/EN — and production already ships an English-only reranker that a live probe found *inverts* French ordering, a failure a per-language lexical index is structurally immune to. Every proper noun in the query set (Fireball, Owlbear, Cloud Dragon) is a common in-vocab D&D term the embedder saw in training — so "dense already handles proper nouns" was only tested where dense is strongest, never on OOV/homebrew/invented names.

**Fair re-test (smallest that would actually settle it):**
- **Corpus:** ~8–15 PDFs from the *real* library, ≥4 systems, both languages, incl. 2–3 French/mixed books and ≥1 homebrew/third-party PDF with invented names the embedder never saw.
- **Queries:** ~60–80 in **explicit categories** so the average can't bury a per-category win: (a) exact-name stat-block/spell/item, (b) OOV/invented/homebrew names + stat codes (`THAC0`, `DC 15`), (c) French exact-token (accented names, French rules terms), (d) mixed FR/EN, (e) exact-phrase/rare-token, plus a paraphrase-prose control. Avoid the `system-name-in-query` cross_system pattern (BM25's artifact worst-case) unless a source/system filter is applied.
- **Metric:** **not** page-overlap MRR@5 — manually deduped top-1-answer-contains or graded relevance / nDCG@10 on the specific answer chunk (the deferred blind scoresheet scaffold is the right shape). Report per-category.
- **BM25 config:** heading-prepended BM25 index (the built-but-unfused V4) so both sides get the heading signal; **per-language analyzer** (snowball-fr with diacritics preserved for French); tuned fusion (sweep dense:BM25 weight or normalized convex fusion, optionally gate BM25 to lexical-heavy categories) instead of uniform k=60. Pure-Python (`rank_bm25`/`bm25s`/`tantivy`/FTS5) — no ML deps, ~5ms.
- **Success criterion:** BM25 must show **complementary recall** the dense pipeline misses (French/OOV/exact-name answers dense fails on) **or** a per-category lift on exact-name/French with no aggregate regression. If it shows neither on the real multilingual corpus, it stays rejected — this time on evidence covering your actual regime. Burden of proof stays on the re-test.

---

## Validation note

Any accuracy change above should be run through the experiments-repo harness (`queries.yaml` ground truth + `score_retrieval.py`, MRR@5/recall@5 on **deduped parents**, with blind manual scoring as the real discriminator since the auto-metric saturates). The harness currently lives only in the experiments repo and is **English-only** — item 16 (wire it into production + add French queries) is a prerequisite for trusting the rest.

---

## Appendix — findings that were refuted and dropped

Recorded so they aren't re-investigated:

1. **"l2→cosine migration bug collapses old scores"** — can't occur: the cosine pin, the nomic→bge-m3 dimension change, and drop-and-recreate delete-index all shipped together in v2.0.1, so any pre-switch library is force-migrated (dimension mismatch → mandatory reindex) before it could exhibit the bug. (Raised twice, both refuted.)
2. **"Prose chunks show a wrong multi-page citation"** — the user-visible page range comes from the *parent* (`server.py:3043`), not the per-chunk stamp; the displayed span correctly describes the parent text returned.
3. **"Ollama-down surfaces as a raw 500"** — the UI already polls `check_ollama_health` and shows "Ollama isn't running — start it to search" ahead of the error branch. (Residual: the MCP path is still opaque on this — minor.)

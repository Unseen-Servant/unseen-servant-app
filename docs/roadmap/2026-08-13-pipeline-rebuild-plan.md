# Pipeline Rebuild Plan — Ingestion & Retrieval v3

**Date:** 2026-08-13
**Scope:** Full greenfield rebuild of the PDF ingestion and retrieval pipeline — extraction → structure → chunking → indexing → query → rank → assembly — plus the storage layer and the sidecar's internal architecture.
**Constraints (locked):** Strictly local — no cloud calls, ever. ONNX-not-PyTorch for anything packaged. Indexing may get slower if quality jumps (target: still under ~15 min for a 400-page book). Search must get much faster *and* much better. **English-first** — the library is predominantly English; French becomes an additive later phase, not a design driver. Queries arrive as **keywords or natural language**, both first-class. The pipeline must serve **small local LLM consumers (Qwen3.5-4B class)** as well as the app UI and Claude.
**Method:** Built on the 2026-07-01 roadmap's verified findings, the eight completed experiment spikes (the ninth, `marker_docling_spike`, was never run — see §6), the production eval baselines, and a full read of the current sidecar.

---

## 0. Diagnosis — what "abysmal" decomposes into

The rebuild targets ten root causes, each verified in code or live-reproduced. Everything else in this plan exists to kill these.

**Speed** — a warm reranked search costs 1.4–7.1 s; the ceiling is structural, not tunable:

| # | Root cause | Where it lives today |
|---|---|---|
| S1 | Cross-encoder rerank is the entire latency budget (0.2–0.8 s off vs 1.4–7.1 s on), and runs **twice** (pool pass + straggler rescore) | `server.py:2028-2116`, `reranker.py` |
| S2 | Query embedding is a blocking HTTP call to Ollama; a cold model load costs seconds, papered over by a 240 s keepalive ping thread | `server.py:942-946, 978-1010` |
| S3 | Parent fetch is an N+1: one connection per search but schema DDL re-executed on every call, then per-result neighbor walks issuing one `SELECT` at a time in both directions | `parents_store.py:46-59, 155-185, 210-232` |
| S4 | Per-request disk I/O: settings JSON every request, manifest JSON up to 3×, `collection.count()` twice on hybrid | `server.py:608-647, 326, 1811, 1885` |
| S5 | BM25 index and spell vocabulary are rebuilt from a **full collection scan** on first use, invalidated by chunk-*count* (not content), and never persisted | `lexical.py:47-65`, `server.py:3659-3685` |

**Relevance** — the well-measured retrieval core sits on extraction it can't trust:

| # | Root cause | Evidence |
|---|---|---|
| R1 | Two-column reading order is never reconstructed — the Dragonbane FALLING rule returns with sentences interleaved: *factually wrong, with a correct citation attached* | roadmap item 10 |
| R2 | Heading promotion produces junk breadcrumbs that outrank real content (stale "Level 5 Cleric Spells" covering most of Wight-Box at 0.999; OSRIC rooted at "CONTENTS") — and breadcrumbs feed the embedding *and* the reranker, so bad headings poison ranking | roadmap item 9 |
| R3 | Embeddings were silently truncated at ~2048 tokens in production (not bge-m3's 8192) — every spike number assumed untruncated; production shipped a log-only probe, not a fix | table-linearization design, `server.py:949-975` |
| R4 | The biggest ranking knob has no trustworthy verdict: rerank shipped default-on against the only recorded experiment (a NO-GO), and the one eval-justified default flip was reverted the same day by real-library disagreement. (It also inverts French queries — retained as a skip-guard edge case, no longer a design driver.) | roadmap §0.2, search-settings design |
| R5 | `chunker_version`/`embedding_model` are written but never read — no shipped fix reaches an already-indexed library, silently | roadmap item 15 |

And one meta-cause that outranks all ten: **the eval harness cannot adjudicate the decisions that matter.** Three English books, ground truth once found 30% wrong (a +0.228 MRR swing — larger than most deltas treated as decisive), page-overlap saturation, blind manual scoresheets generated but never scored in 3 of 4 spikes, and the one rerank default flip it justified was reverted the same day by real-library behavior. This is now an explicit design rule, not just a complaint: **spike ranking numbers are priors to re-prove, not settled evidence (§2), and the rebuild is gated on evals we can trust, built first.**

---

## 1. Goals and non-goals

**Goals**

1. Warm search feels instant: **p50 ≤ 300 ms, p95 ≤ 1 s** with the default configuration; no per-query model-load cliffs.
2. Results are right for both entry modes — terse keyword lookups ("goblin AC") and full natural-language questions: reading-order-correct text, trustworthy breadcrumbs, no duplicate sections in the top-10, and **the answer in the top 3** — the bar the weakest consumer (a 4B model) actually needs, since it can't rescue an answer buried at rank 8.
3. Every result carries page + bounding-box provenance, unlocking matched-span highlighting, render-the-source-region, and printed page labels.
4. Pipeline changes reach users: staleness is detected and re-index is prompted, not silent.
5. One command answers "did this change help?" — a harness whose verdicts survive contact with the real library.
6. Small local models are first-class consumers: a Qwen3.5-4B wired over MCP gets compact, token-budgeted, structured payloads it can actually reason over.

**Non-goals**

- No cloud tier of any kind (hard product promise).
- No VLM/OCR extraction as the primary path — `glm_ocr_spike` NO-GO stands (silently drops table columns; that failure profile is exactly stat blocks). OCR appears only as an explicit opt-in for scanned books.
- No LLM table captioning, centroid parents, or hybrid-index dual embedding (all spike NO-GOs; see §6 decision log).
- Not rebuilding the Svelte UI or the Tauri shell. The frontend adapts to a new API; it doesn't get rewritten.
- French/multilingual quality is not a v3 gate. The `lang` fields stay in the schema and the rerank language skip-guard stays in place, so a later French phase is additive, not a re-architecture.

---

## 2. What the rebuild inherits — priors, not gospel

Greenfield does not mean amnesia, but the spike evidence gets demoted on methodological grounds (loose ground truth — once found 30% wrong, a saturating page-overlap metric, blind scoresheets generated but never scored). Split the inheritance in two:

**Integrity findings stand.** They are objective and metric-independent, and constrain v3's design outright: GLM-OCR silently drops table columns; production embeddings truncated at ~2048 tokens; naive breadcrumb grouping produced a 225 000-char parent; single-size top-5s repeat the same section.

**Ranking findings become hypotheses with favorable priors.** Each row below must re-prove itself as its own ablation brick on the Phase 0 harness before it earns a place in the default configuration — Phases 2–3 are structured as exactly this ladder (§4). If a brick doesn't pay on a harness we trust, it ships default-off or dies, whatever the spike said:

| Brick (hypothesis) | Prior from spikes |
|---|---|
| Heading-prepended text for embedding, lexical, and rerank views | +0.184 MRR@5 / +0.150 recall@5 — the single biggest lever ever measured here |
| Table row linearization (`Header: cell; …`) with the coverage-ratio guard and title-row heuristic | +0.152 MRR@5 on table queries, zero regressions, zero LLM cost |
| Atomic tables (never split mid-table; exempt from sub-splitting and averaging) | centroid's table-recall collapse 0.800 → 0.600 is the counterfactual |
| Small-unit / parent-document retrieval with dedupe-by-parent | manual top-1 hit rate 100% vs 50% for single-size; 68% of single-size top-5s contained duplicates |
| Bounded parents (contiguous grouping, ~6 000-char cap) | naive breadcrumb group-by produced a 225 000-char parent |
| Library-vocabulary spell correction with the general-English guard | closes 58% of typo nDCG gap; clean queries reproduce baseline to the digit |
| Game-system soft-boost (×1.5 / ×0.7, query-side) | +0.042 cross-system MRR@5, never hurts |
| Language-aware rerank gating, atomic staged re-index, path-based (not filename) scoping, fuzzy filter resolution with an actionable message, dual-scale relevance tiers | Phase-1 2026-07-09 fixes, all mutation-verified |

Explicitly **killed**: Markdown as the pipeline IR (loses bbox, reading order, and forces regex archaeology like R1–R4 cleanup); Ollama as the embedding runtime; ChromaDB + 4 ad-hoc JSON stores + separate parents SQLite; the in-memory rebuilt-per-boot BM25; mtime-only change detection; the 3 789-line `server.py`; the two-pass rerank; the 10× overfetch heuristic.

---

## 3. Target architecture

### 3.1 Runtime and packaging

**Keep a Python sidecar process; rebuild it as a clean workspace.** Full greenfield puts Rust-native indexing on the table, and it loses on evidence: the entire local document-AI ecosystem (PyMuPDF, layout models, ONNX tooling, the eval harness) is Python-first, and porting pymupdf4llm-equivalent extraction plus a layout stage to Rust is months of work that buys no user-visible quality. The sidecar's *shape* changes instead:

```
sidecar/
  ingest/     extract.py  layout.py  structure.py  chunk.py  linearize.py
  index/      store.py  embedder.py  lexical.py  vocab.py
  query/      pipeline.py  fuse.py  rerank.py  boost.py  assemble.py
  api/        http.py  (thin FastAPI layer; endpoints ≤ 20 lines each)
  domain/     models.py  (IR dataclasses, settings, versioning)
  evals/      (promoted from add-on to first-class, runs in CI)
```

All models run **in-process via onnxruntime** on CPU (the CoreML execution provider often falls back to CPU for transformer ops — measure it in Phase 1, don't assume it). The Ollama dependency is deleted — with it go the install prerequisite, the cold-load cliff, the keepalive thread, and the truncation bug class (R3, S2). This is also a major onboarding win: the app becomes self-contained.

### 3.2 Ingestion pipeline — IR-centric, not Markdown-centric

The current pipeline's original sin is using Markdown as its intermediate representation: bbox and reading order are destroyed at step 1, then four cleanup rules, a heading promoter, and a `<br>`-flattener try to reverse-engineer structure from text. v3 inverts this: **a typed Document IR is the product of ingestion; text renderings are derived views.**

```
PDF ─A→ page text-dict + rasters ─B→ layout regions ─C→ reading order
    ─D→ typed blocks (heading/prose/table/caption/image/artifact)
    ─E→ section tree ─F→ chunks + embed units ─G→ index commit (one txn)
```

- **A. Raw extraction (PyMuPDF).** `get_text("dict")` spans with font/bbox, page rasters at ~150 DPI for the layout model, TOC, printed page labels (`page.get_label()`). Pages with no text layer are flagged `needs_ocr` and surfaced in the UI (opt-in slow OCR pass per book — "slower is fine" budget).
- **B. Layout analysis (ONNX).** A document-layout detector classifies regions: column blocks, tables, headings, captions, page furniture, images. Primary candidate (Phase 1 bake-off; license + ONNX export + CPU latency are the criteria): the **PP-DocLayout family** (Apache-2.0; PaddleOCR 3.x has an official ONNX path, though the newest V2/V3 variants need community-patched conversion — pin whichever converts cleanly). Secondary: `docling-onnx-models` layout packaging. **DocLayout-YOLO is ruled out** (AGPL-3.0 via YOLOv10 — untenable for a distributed proprietary app); Surya/Marker are ruled out on model-license grounds. Budget ≤ ~200 ms/page CPU. This stage replaces cleanup R2/R4 (running headers become classified `artifact` regions, dropped with confidence rather than 40%-frequency regex) and is the structural fix for **R1**: region-level XY-cut gives column-correct reading order instead of trusting pymupdf4llm's block order.
- **C/D. Ordered typed blocks.** Text spans are assigned to regions; regions ordered by column-aware XY-cut. Every block keeps `page`, `bbox`, `font_stats`.
- **E. Section tree.** Headings come from three agreeing signals — layout regions typed `heading`, font clustering (carried over, now italic-aware), TOC depth-1 pinning — with junk-heading rejection (stat-line/caption shapes, staleness caps) fixing **R2**. Output: a real tree (`section_id`, parent, level, title, page span), persisted. Parents in retrieval become section nodes with the 6 000-char cap; stat-block sub-section stitching ("Solar" + its "Actions") becomes a tree-prefix query instead of the current 5-line-hack-that-never-shipped.
- **F. Chunking.** Structure-aware boundaries as today (heading/table walls, ~1 000-char soft cap, no overlap — validated), then small embed units (~400-char prose splits; per-row table linearization with coverage guard). Every chunk and unit carries `section_id`, page span, **bbox spans**, and `lang` (per-block language ID; the library is mixed FR/EN).
- **G. Commit.** One transaction per document: sections, chunks, units, vectors, FTS rows, vocab deltas, manifest row with `pipeline_version`. Content-hash change detection (mtime as a fast-path hint only). Rename = pure metadata update (hash-keyed, no re-embed) — one implementation, not three copies.

Two-pass indexing to honor the "searchable fast, refined later" instinct while staying in budget: pass 1 (extract+layout+structure+chunk) makes a book browsable in ~1–2 min; pass 2 (embedding) streams in the background with per-book progress. Target for a 400-page book on an M-series laptop: **≤ 15 min total**, extraction ≤ 4 min.

### 3.3 Storage — one SQLite database

ChromaDB + `parents.sqlite3` + `index_manifest.json` + `collections.json` + `custom_game_systems.json` + `search_settings.json` collapse into **one SQLite file** (WAL mode), which is the system of record:

```
documents(id, path, content_hash, mtime, size, page_count, toc, page_labels,
          game_systems, status, needs_ocr, pipeline_version, indexed_at, last_error)
sections (id, doc_id, parent_id, level, title, page_start, page_end, ordinal)
chunks   (id, doc_id, section_id, ordinal, kind, text, page_start, page_end, bbox_spans)
units    (id, chunk_id, text, lang)          -- embed/lexical view is heading-prepended
unit_fts (FTS5: text, heading; porter/english now — `lang` reserved for a later French pass)
vectors  (unit_id, embedding)                -- engine per §Phase-1 bake-off
vocab    (term, lang, freq)                  -- persisted; incremental per-document deltas
collections / settings / custom_systems     -- plain tables
```

Wins: transactional consistency (a crashed index never leaves Chroma and the manifest disagreeing), no orphan-segment GC hack, S3/S4/S5 die (parents = one `WHERE section_id IN (...)` batch; settings/manifest live in memory with event invalidation; FTS and vocab are persisted and updated incrementally per document commit).

**Vector engine** is a Phase 1 bake-off with a hard gate (top-200 filtered query over 200 k × 1024-dim units in ≤ 50 ms warm): `sqlite-vec` vs an embedded ANN index (usearch HNSW / LanceDB) sitting beside SQLite. sqlite-vec is brute-force only, so it competes **exclusively** in its documented binary-quantization-prefilter → full-precision-rescore configuration (a raw f32 scan at this scale is ~800 MB/query — instant disqualification). Prefer the one-file story unless the gate fails.

**Embedder:** bge-m3 dense, int8 ONNX, in-process — same model family, so spike evidence transfers, now actually run at full context with per-unit token counts logged. Note: these are community ONNX exports (BAAI ships none, and fastembed does not support bge-m3) — the Phase 1 spike pins one export and verifies vector parity against Ollama f16 (cosine drift < 0.01 on 1 k units) before anything else builds on it. Batch ~64–256; throughput gate ≥ 25 units/s CPU. Fallback if a gate fails: a smaller multilingual embedder re-validated on the Phase 0 harness — model choice is an eval-gated decision, not an aesthetic one.

### 3.4 Query pipeline

```
query → query-shape signals (keyword vs natural-language) → spell-correct (library vocab + English-dictionary guard)
      → [dense top-K ‖ BM25 top-K]  (same SQL prefilter: paths/systems/collections)
      → weighted fusion (tuned on Phase-0 evals, not uniform RRF k=60)
      → game-system soft-boost
      → optional rerank: multilingual ONNX cross-encoder, ONE pass, pool ≤ 25
      → dedupe by section → assemble parents (single batch query)
      → results {text, matched_text, bbox, printed page label, tier, lang}
```

Design points, each answering a diagnosed cause:

- **Hybrid is the mechanism that serves both query styles.** Keyword queries ("goblin AC", "fireball 5e") are lexical's home turf — short, proper-noun-heavy, no sentence semantics for the embedder to work with; natural-language questions are dense's. The old BM25 NO-GO doesn't bind here (its re-test was already reopened: weakest-possible fusion config, on a corpus and metric blind to BM25's exact-token/OOV/homebrew edge). v3 builds it right — heading-prepended FTS, tuned fusion weights, optionally conditioned on query shape (short/OOV-heavy → lexical-leaning) — and the Phase 0 harness, with keyword and NL queries as separately scored categories, decides the default.
- **Rerank becomes cheap — and finally gets a verdict.** One pass, pool 25 (down from 50 + a second straggler-rescore pass). English-first widens the candidate list to small fast English cross-encoders (MiniLM-class ONNX int8 — tens of ms for the whole pool) alongside **bge-reranker-v2-m3** (Apache-2.0, maintained `onnx-community` export, int8 — heavier but stronger, and buys multilingual for free later). The French skip-guard behavior is retained. Phase 1 gates latency; Phase 3's ablation ladder gives rerank the trustworthy on/off/which-model verdict it has never had — the knob stays user-visible either way. Budget ≤ 500 ms; if no candidate meets both gates, default flips to off and the tier system leans on calibrated cosine — the harness finally settles the contradiction that caused the same-day default revert.
- **No 10× overfetch magic** — candidate depths are per-stage tuned constants with eval evidence.
- **`matched_text` + bbox** ship in the payload (roadmap item 11), enabling highlight-and-scroll and region rendering in the UI, and a `get_pages(filename, start, end)` MCP tool (item 14) gives Claude drill-in.

**Latency budget (warm, M-series, default config):**

| Stage | Budget |
|---|---|
| Spell + lang-ID | ≤ 5 ms |
| Query embed (in-process) | ≤ 40 ms |
| Dense + BM25 (parallel) | ≤ 60 ms |
| Fusion/boost/dedupe | ≤ 10 ms |
| Rerank (pool 25, optional) | ≤ 500 ms |
| Parent assembly | ≤ 10 ms |
| **Total** | **≤ 125 ms rerank-off / ≤ 625 ms rerank-on** |

Cold start: models mmap at app launch in the background; first search pays ≤ 2 s once per session, never mid-conversation.

### 3.5 API surface — three consumers, one contract

The HTTP API is redesigned (greenfield scope): versioned `/v1/` routes, a single `SearchResponse` shape carrying the new fields, SSE indexing streams kept (they work well). The Tauri frontend migrates in one PR per surface; the eval harness pins the new contract.

The consumer list is explicitly three: the app UI, Claude Desktop, and **small local models (Qwen3.5-4B class) wired to the MCP server**. The small models set the hardest constraints, so the surface is designed to them:

- **Compact by default.** Today's MCP default returns full parents — ~24 k chars per call — which drowns a 4B model's context and reasoning. v3 returns `matched_text`-centered snippets with breadcrumb + citation first; parent text on request.
- **Token-budgeted.** A `max_context_chars` parameter on `search_library`; the server packs the best results into the budget instead of truncating blindly.
- **Drill-in over dump-out.** `get_pages(filename, start, end)` and `get_section(section_id)` let a model fetch exactly the region it needs — cheaper for small contexts than big speculative payloads.
- **Precision@3 is the headline metric.** A 4B model reliably uses what's in its top 3 and cannot rescue rank 8 — the harness scores it per category and retrieval decisions optimize for it.

---

## 4. Phased delivery — every phase has a gate

**Phase 0 — An eval harness we actually trust (≈ 1–1.5 weeks).** Everything else is gated on this; it's the cheapest phase and the load-bearing one — no brick lands without its verdict.
- Corpus: 8–15 **English** PDFs from the real library — ≥ 4 systems, ≥ 1 homebrew/third-party PDF with invented names, the known pathological pages (Dragonbane FALLING, OSRIC, Wight-Box) as golden pages. A couple of French books may ride along as non-gating canaries.
- Queries: 60–80, written in **paired styles — a keyword form and a natural-language form of the same intent** ("goblin AC" / "what armor class does a goblin have") so both entry modes are separately scored categories — across: exact-name stat/spell/item, OOV/homebrew names, table lookups, prose rules, cross-page, paraphrase control.
- Grading that fixes the old harness's failure modes: answer anchors on the specific chunk (no page-overlap saturation), independently re-verified ground truth (the old set was once 30% wrong), per-category reporting, **precision@3 / answer-in-top-3 as the headline** alongside nDCG@10 and MRR@5, latency percentiles, and payload size per call (the small-model budget metric).
- **Actually run one blind manual scoring round** (the discriminator that inverted a spike verdict, deferred 3 of 4 times).
- Gate: current v2 pipeline baselined on the new harness → the number every brick must beat.

**Phase 1 — Foundation bake-offs (≈ 1 week).** Small spikes with hard gates, in the experiments repo per house rules:
- Layout model: accuracy on 30 golden pages (columns, tables, furniture) + ≤ 200 ms/page CPU + license + ONNX.
- In-process embedding: bge-m3 ONNX int8 ≥ 25 units/s, full-context verified by construction, parity vs Ollama vectors on 1 k units (cosine drift < 0.01 or re-baseline).
- Vector engine: the 50 ms gate above, plus filtered-query correctness.
- Reranker candidates (MiniLM-class English + bge-reranker-v2-m3): ≤ 500 ms/25 pairs CPU int8; the which-model/on-off verdict itself is deferred to the Phase 3 ladder.
- Gate: every slot has a winner or a documented fallback; no phase-2 code before this.

**Phase 2 — Ingestion v3 (≈ 2–3 weeks).** Stages A–G on the new storage, golden-page snapshot tests per stage, two-pass indexing, OCR-needed detection. Gate: real-library index completes end-to-end; extraction golden tests pass; Dragonbane FALLING reads in order; junk-breadcrumb rate on Wight-Box/OSRIC audited < 2%; 400-page book ≤ 15 min.

**Phase 3 — Retrieval v3 as an ablation ladder (≈ 2 weeks).** The query pipeline is assembled brick by brick, each rung a committed baseline on the Phase 0 harness, kept only if it pays:

`dense-only` → `+ heading-prepend` → `+ table row units` → `+ parents & dedupe` → `+ BM25 fusion (weight sweep, query-shape conditioning)` → `+ system boost` → `+ spell correction` → `+ rerank (per candidate model)` → `+ tier calibration`

This is how the untrusted spike numbers get replaced: every prior in §2 either re-proves itself here under strict answer-chunk grading or ships default-off/dies. Baselines committed per rung (the `evals/baselines/` convention already exists). Gate: the final configuration beats the v2 baseline on precision@3, nDCG@10 and MRR@5 overall **and** on the keyword and OOV categories, with zero duplicate-section top-10s, inside the latency budget.

**Phase 4 — Integration and cutover (≈ 1–2 weeks).** New API + frontend/MCP migration; migration tooling: detect old data dir, import collections/settings/tags, prompt full re-index (`pipeline_version` finally read at startup — R5 dies); side-by-side A/B window where the harness runs both pipelines on identical requests; old path deleted at the end, not maintained.
Gate: all frontend/MCP flows green; migration from a real v2 library verified; CHANGELOG + docs.

**Phase 5 — The payoff layer (ongoing, post-cutover).** Matched-span highlight + render-source-region in results (fixes macOS open-at-page), printed page labels in citations, `get_pages`/`get_section` MCP tools, TOC/bookmark navigation (feeds the "Intuitive Navigation" product roadmap item), opt-in OCR pass for scanned books, and a **small-model smoke test**: wire an actual Qwen3.5-4B over MCP and verify it answers ~20 eval questions correctly from the compact payloads — the end-to-end proof of the consumer requirement. A later **French phase** (French queries, stemming, reranker verdict) slots in here without re-architecture.

Solo-builder total: **7–10 weeks**. If it must shrink: Phase 5 is deferrable, Phase 4's A/B window can compress, and the reranker can ship as "off by default, knob retained" if its gates fail — but Phase 0 and the layout stage are the two things that must not be cut; they are the rebuild.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Layout model underperforms on art-heavy TTRPG pages | Golden-page gate in Phase 1; per-page fallback to pymupdf4llm-style extraction (confidence-scored), so a bad page degrades to today's quality, never below |
| ONNX packaging bloat/breakage (the symspellpy data-file incident, at model scale) | Packaged-app smoke test in CI from Phase 1 on: fresh install → index sample → search, on a clean macOS runner |
| bge-m3 int8 quality drift vs Ollama f16 | Parity check in Phase 1; harness re-baseline if drift is real |
| sqlite-vec scan cost at large libraries | The 50 ms gate at 200 k units decides; ANN fallback is pre-scoped, storage schema is engine-agnostic |
| Full re-index annoys existing users | Two-pass indexing (browsable in minutes), progress UX exists, staleness banner explains *why*; old index keeps serving until cutover completes |
| Solo-project scope creep | Phase gates are binary; anything failing its gate ships behind a default-off knob rather than blocking cutover |

---

## 6. Decision log

| Decision | Rationale | Reopen if |
|---|---|---|
| Python sidecar retained (greenfield internals, not greenfield language) | Doc-AI ecosystem is Python; a Rust port is months for zero user-visible quality | Packaging pain exceeds a release cycle's work, or a Rust extraction stack reaches parity |
| Typed IR replaces Markdown as pipeline currency | Four cleanup regex rules + heading promotion are reverse-engineering structure Markdown destroyed; bbox provenance is impossible otherwise | — |
| In-process ONNX embeddings; Ollama dependency removed | Kills S2 + R3 + install prerequisite; same model family preserves evidence | Phase 1 throughput/parity gates fail |
| One SQLite store | Transactionality, S3/S4/S5, backup story | Vector gate fails → hybrid file layout |
| Hybrid lexical+dense default-on *candidate* | Keyword queries are a first-class entry mode and lexical's home turf; prior NO-GO tested the weakest config on a corpus blind to BM25's edge | Phase 3 ladder shows no keyword/OOV win per the pre-registered criterion |
| Rerank single-pass, small-pool, model open | Two-pass rerank owns the v2 latency budget; the on/off/which-model verdict is deferred to the Phase 3 ladder (English-first widens candidates to MiniLM-class) | Gates in Phases 1/3 |
| English-first scope | Library is predominantly English; French skip-guard retained, `lang` fields reserved so a French phase is additive | French share of the library or its priority grows |
| Spike ranking numbers demoted to priors | Methodology wasn't strict on ranking accuracy (loose GT, saturating metric, unscored blind sheets); integrity findings exempt — every brick re-proves itself on the Phase 0 harness | — |
| Small local LLMs are first-class consumers | Qwen3.5-4B-class models need compact, token-budgeted, precise payloads; precision@3 becomes the headline metric | — |
| VLM/OCR not in the main path | glm_ocr NO-GO: silent column drops on exactly stat-block shapes; "correct-ugly beats wrong-clean" | A ≥ 7B local VLM passes the 4+-column table probe within packaging budget |
| `marker_docling_spike` closed as superseded | The roadmap reserved the extractor-swap question for that never-run spike. v3's layout stage answers the same defects it was meant to settle (reading order, heading corruption, flat headings) with permissively-licensed ONNX models — Marker (Surya license) and Docling-PyTorch fail the packaging constraint anyway | The Phase 1 layout bake-off fails its golden-page gate — then run the spike for real against `docling-onnx-models` |
| No captioning / centroid / dual-index | Spike NO-GOs (strict-subset value / table-recall collapse / +14% storage for noise) | — |

---

## 7. Workspace setup

No third repo. The two existing repos already map onto the two kinds of work, and the focused space comes from a directory boundary, not a repo boundary:

- **Phase 1 bake-offs → the experiments repo**, as ordinary spikes (`layout_model_spike`, `embed_parity_spike`, `vector_engine_spike`, `rerank_latency_spike`). Its house rules — time-boxed, write-once FINDINGS, no cloud calls — are exactly the discipline these need.
- **Phase 0 harness + Phases 2–4 → the app repo, in a parallel top-level `sidecar-v3/`** on `main` (strangler pattern), not a long-lived branch: over 7–10 weeks a branch drifts against every v2 hotfix, while a parallel directory never conflicts. `sidecar-v3/` gets its own `pyproject.toml`/uv project, its own test suite and CI job, and its **own `CLAUDE.md`** whose first line points at this plan as the constitution. It is excluded from packaging until Phase 4 cutover, which then becomes a packaging switch + directory swap, not a repo transplant.
- **The harness is engine-agnostic and lives at top level (`evals/`)**, driving v2 or v3 through the same request shape via a `--engine` flag — required anyway, since Phase 0 must baseline v2 and Phase 4 runs both sides A/B on identical requests. Per-rung baselines commit to `evals/baselines/` as today.
- **The corpus is never committed** (real-library PDFs are copyrighted). Commit a manifest — path, SHA-256, page count — plus a verify script; the harness refuses to run against a corpus that doesn't match the manifest, which also protects ground truth from silently drifting when a PDF gets re-downloaded.
- **One milestone per phase; one PR per ablation rung**, with the rung's baseline JSON in the PR — the eval delta *is* the review.

## Appendix — current pipeline, one paragraph

For orientation: v2 is `pymupdf4llm` per-page Markdown → font/TOC heading promotion (`toc_then_font`) → regex cleanup in load-bearing order R1 fragment rejoin → R3 image chrome → R4 heading furniture → R2 header/footer → `<br>`-cell flatten → structure-aware chunking (1 000-char soft cap) → 400-char embed units + per-row table linearization → bge-m3 via Ollama HTTP → ChromaDB (cosine) + parents SQLite + 4 JSON side-stores → query: settings/manifest JSON reads, symspell correction, dense (10× overfetch) ± in-memory BM25 RRF, system boost, two-pass English-only cross-encoder rerank, parent dedupe, N+1 parent stitch. Eval: 40 locked queries (+25 typo variants scored separately) over 3 English CC books; rerank-on baseline nDCG@10 0.644 · MRR@5 0.584 · recall@10 0.850. Its measured wins are carried into v3 (§2); its structural debts are the reason v3 exists (§0).

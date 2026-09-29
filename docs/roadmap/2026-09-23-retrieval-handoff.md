# Retrieval workstream — handoff, 2026-09-23

Where the v2 retrieval roadmap stands and what is left. Written to pick the work up cold. The roadmap itself is `2026-09-02-v2-retrieval-improvement-roadmap.md` (§5 bars, §8 decision log).

## State on main (all pushed, CI green)

| phase | what | commits | closed |
|---|---|---|---|
| 0 | measurement: tagged corpus, twin rule, breadcrumb-qa, library tier, blind round | dd4651b..0237911 | 2026-09-02 |
| 1 | index side, one reindex: heading sanitation, promotion quality, `section_id`/`section_path`, page spans, `pipeline_version`, persisted FTS5 | bfcf2c1..d80c235 | 2026-09-12 |
| 2 | query time, no reindex: sections by path prefix, `max_context_chars` packer, MCP compact + `get_section`/`get_pages`, near-dup collapse with `also_in`, request-scoped reads + persisted spell vocab + warm-up, UI highlight/GFM/chips/labels | 045a4c4..d88ad48 | 2026-09-12 |
| blind rounds | headings sheet scored by Jerome (κ 0.743); labels carried onto sections by `evals/blind/transfer.py` | bb923d4, 9c35213 | 2026-09-23 |

**Reference baseline for Phase 3+: `evals/baselines/2026-09-12-v2-sections`** (gate against it, not headings).

**Update 2026-09-23 — 3.1 and 3.3 landed** (roadmap §8 row). New baselines `2026-09-23-v2-boost` (production default) and `2026-09-23-v2-hybrid` (3.3 + `--hybrid`, all 0.879 / cued 0.771 / keyword 0.912, p50 1 265 ms). Gate 3.2 against **`2026-09-23-v2-hybrid`** with `--hybrid`: hybrid flips default-on once 3.2's p50 fits.

**Update 2026-09-24 — 3.2 landed, hybrid default-on** (roadmap §8 row, commit 8b00088). int8 L-6 cross-encoder, hard reorder (the RRF blend lost on v2), scoring-only straggler pass. **New reference baseline: `evals/baselines/2026-09-24-v2-rerank`** (run with `--hybrid`, since production is now hybrid): all 0.884 / cued 0.771 / single 0.948 / uncued 0.942 / keyword 0.926, warm p50 358 ms. Gate 3.4+ against it with `--hybrid`. Remaining Phase 3: **3.4 tier calibration** (#366 — thresholds now sit on the L-6 sigmoid scale, so refit them) and the optional **3.5** spell tie-break. The real library still needs a reindex for hybrid to have FTS rows there.

**Update 2026-09-24 — 3.4 landed** (§8 row): rerank tiers strong ≥ 0.98 / weak < 0.5, fit on carried blind labels; real library (reindexed 2026-09-24) now 27 % strong. MCP weak divider opens the trailing weak run. Phase 3 is complete except the optional **3.5** spell tie-break; next is **Phase 4** (blind round on the final configuration, library tier queries in `evals/retrieval/library.yaml`, CHANGELOG, release tag) and the Phase 5 decision (roadmap §4). Quick exploratory runs: `--reuse-index --data-dir evals/.eval_data/v2-p3 --no-write --no-index` (current pipeline, deterministic, ~2 min); `evals/.eval_data/v2` is stale (no FTS rows — the harness's idempotent indexing ignores `pipeline_version`).

**Update 2026-09-24 — 3.5 landed (59b0f1c); Phase 4 cut down to the release** (§8 rows). No new blind round (transferred labels on `2026-09-24-v2-rerank`: human single 0.906, readable@5 0.979, 70 % covered) and no library tier this release. What remains: licence gate (`scripts/check-third-party.py --release` fails — see below), `bump-version.sh 3.0.0`, date the CHANGELOG `[3.0.0]` entry, local `npm run tauri build` + `scripts/build-sidecar.sh`, tag `v3.0.0`. Then the Phase 5 decision.

**Update 2026-09-24 — v3.0.0 shipped (published, renamed Unseen Servant); Phase 5 decided.** Both swaps GO (roadmap §8 last row): runtime (Ollama → ONNX) first as v3.1.0, store (Chroma → sqlite-vec) as v3.2.0, both after the workstation's move-only sidecar split and before Command. The cross-workstream order lives in `2026-09-24-unseen-servant-workstation-architecture.md` §6. The licence blocker below is moot — the app is personal-use only since 2026-09-24 and the release gate was dropped (703765d).

**Release blocker (2026-09-24, superseded):** `third_party/components.json` has 8 non-approved entries, and release mode fails closed. The shipped v2 sidecar's `pymupdf4llm` / `PyMuPDF` are `blocked` (AGPL); the rest are v3-era entries (pypdfium2, pdfplumber, pdfminer.six, PP-DocLayout-M) that v2 does not ship, plus the bge-m3 and MiniLM-L6 exports, which need their actual shipped forms (Ollama bge-m3; Xenova int8 L-6 via fastembed) recorded. The inventory also omits things the v2 sidecar does ship (chromadb, fastembed, symspellpy and its bigram list, Ollama as a prerequisite).

| measure | phase0b | headings | sections | bar |
|---|---|---|---|---|
| auto all MRR@5 | 0.766 | 0.790 | 0.862 | ≥ 0.82 |
| auto single | 0.753 | 0.767 | 0.948 | ≥ 0.82 |
| auto cued | 0.632 | 0.701 | 0.722 | ≥ 0.72 |
| auto uncued | 0.942 | 0.925 | 0.925 | |
| cross_page MRR@5 | 0.417 | 0.354 | 1.000 | ≥ 0.75 |
| human single (blind) | 0.87 | 0.88 | 0.906 (transferred) | ≥ 0.90 |
| readable@5 (blind) | 0.965 | 0.962 | 0.971 (transferred) | ≥ 0.98 |
| warm p50, rerank on | 1 274 ms | 1 094 ms | 1 126 ms | ≤ 500 ms |
| warm p50, rerank off | | | 76 ms | ≤ 200 ms |
| payload, unbudgeted / @8k | | 37 294 | 44 203 / 6 457 | ≤ 8 000 top-3 intact |

Bars still open: auto cued 0.722 sits on the line; human single 0.906 vs 0.90 and readable 0.971 vs 0.98 are close; warm p50 with rerank is the big one and is Phase 3's job.

## Next: Phase 3 — ranking polish (roadmap §4, ≈ 1 week, no reindex)

Rungs land in the v3 ladder's order so each baseline isolates one brick; every rung is a `--baseline <name> --gate evals/baselines/2026-09-12-v2-sections.json` run (~40 min, Ollama up).

1. **3.1 Hybrid default-on.** Query side of the persisted FTS5 from Phase 1: stopword-stripped `OR` query over the spell-corrected terms, same scope on both channels, weighted RRF dense 1.0 : lexical *w* swept 0.2–0.5 (`--lex-weight`; v3 landed 0.3, 1:1 nicked NL). Pre-registered bar: no scope and neither style regresses vs sections at the chosen weight; keyword MRR@5 up; exact_name recall@5 up; latency ≤ +30 ms. If no weight clears it, ship the best non-regressing weight and log it. Port from `sidecar-v3/query/pipeline.py` (`_fts_query`, `_STOPWORDS`) and `fuse.py` (weighted `rrf`). `sidecar/lexical.py` already has `PersistedLexicalIndex` and an unweighted `rrf_fuse`.
2. **3.2 Rerank rebuild.** Single pass over the fused order, pool 25–50, `ms-marco-MiniLM-L-6-v2` int8 ONNX (asset in `sidecar-v3/models/`), score **blended** by weighted RRF (sweep 0.3–0.7; v3 landed 0.5), never a hard override; delete the straggler pass; table units fed as `header: cell` rows. Bar: p50 ≤ 500 ms, single ≥ sections. The 07-10 L-6 NO-GO was a hard reorder; the blend is what v3 measured as +0.024.
3. **3.3 Boost as a stable partition after rerank** (port `sidecar-v3/query/boost.py`): named-system sources move to the front, order within partitions preserved, never a filter. Bar: cued ≥ 0.65, single/uncued identical.
4. **3.4 Tier calibration** (#366): thresholds fit on the blended score over the real library (`sidecar/evals/library_probe.py`), target ≤ 35 % `strong`; one scale whether or not rerank ran; the MCP weak divider inherits.
5. **3.5 Spell tie-break** (optional): prefer the library-vocab candidate when its corpus frequency is non-zero.

Planning note: write the plan with `superpowers:writing-plans` the same way as Phases 1–2 (explorer maps first, briefs per task, subagent-driven execution with a ledger under `.superpowers/sdd/<plan>/`). The three explorers to run first: the current `_search_sync` stage map (fusion block, boost, rerank head/straggler, dedupe, format), `sidecar-v3/query/` for the bricks to port, and `evals/run_eval.py` knob plumbing (`--lex-weight`, `--rerank-weight` already exist as `extra`).

## Phase 2 residuals worth folding into Phase 3

- **Printed page labels** are blanked whenever the returned span is wider than the matched unit (Phase 2 ruling); a `page_label_start/end` pair on the parents rows would restore them without touching Chroma. Reindex-free only if written by a one-off backfill from the PDFs.
- **Cued auto over-grades** by ~0.08 vs human on both baselines: anchors accept the twin edition's chunk where the human rejects it. Fix on the anchor side (`evals/retrieval/queries.yaml` q043/q044 style `doc` lists are the precedent) before tuning boost on cued numbers.
- **Spell vocabulary coverage check** is aggregate (`rows >= sum chunk_count`); per-source would close the orphan-rows gap.
- **Table hits highlight the whole parent block**, not the row; a character offset from the sidecar would be needed for row precision.
- **`get_section` container-id fallback** is a `LIKE '%id%'` scan (rare path, correct, unindexed).
- **`where_to_sql` degenerate shapes** (`{"$or": []}`, `{}` in a list) are unreachable today; guard them before hybrid goes default-on and new clause shapes appear.
- **Spell corrector still scans Chroma on first use on legacy stores** (no FTS rows); the S5 residue. Goes away with reindex.
- Filled clickable `also_in` chip vs the "no filled-rectangle buttons" convention — Jerome's design call.

## Not measured / not done

- **Real library**: no reindex of the app's own library yet. Library settings shows the "N files indexed with an older pipeline" note; after reindexing run `sidecar/evals/library_probe.py` (breadcrumb: markup ≤ 2 %, furniture 0, split 0) and, once `evals/retrieval/library.yaml` has ≥ 20 queries (Phase 0 Task 6.10, still unauthored), `--suite library --data-dir <app data dir>`.
- **Phase 4** (blind round on the final configuration, library tier, CHANGELOG, release tag) and **Phase 5** (Chroma → sqlite-vec, Ollama → ONNX; decided at the END of Phase 3 by the rule in roadmap §4).
- Closed 2026-09-24 with pointers to the commits: #367, #328 (Phase 1), #375 (on v2), #343, #341 (Phase 2), #366 (3.4).

## How to run things

```bash
# retrieval baseline (Ollama up with bge-m3; ~40 min; writes evals/baselines/<date>-v2-<name>.*)
OLLAMA_CONTEXT_LENGTH=8192 uv run --project sidecar python -m evals.run_eval --engine v2 \
    --baseline <name> --gate evals/baselines/2026-09-12-v2-sections.json
# knobs: --hybrid --lex-weight W --rerank-weight W --no-rerank --max-context-chars N
# breadcrumb / extraction gates (no Ollama, ~8 / ~3 min)
uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa --gate evals/baselines/2026-09-11-v2-breadcrumb-qa.json
uv run --project sidecar python -m evals.run_eval --engine v2 --suite extraction --gate evals/baselines/2026-09-11-v2-extraction.json
# blind round: generate → serve → score; or carry earlier labels forward
uv run --project sidecar python -m evals.blind.generate evals/baselines/<stem>
(cd evals/baselines && python3 -m http.server 8765)   # http://localhost:8765/<stem>.blind.html
uv run --project sidecar python -m evals.blind.score evals/baselines/<stem>
uv run --project sidecar python -m evals.blind.transfer evals/baselines/<scored-stem> evals/baselines/<target-stem>
# suites
uv run --project sidecar pytest sidecar/tests -q          # 739
uv run --project sidecar-v3 pytest evals/tests -q         # 86
npm run check && npm run lint:css && npm test             # 462 vitest
(cd src-tauri && cargo test && cargo clippy -- -D warnings && cargo fmt --check)
```

## Gotchas learned the hard way

- **1Password locks** and every signed commit then fails with `1Password: failed to fill whole buffer` or `agent returned an error`. Never `--no-gpg-sign`; leave the work staged, keep the message in a file, retry when unlocked. It stalled Phases 1 and 2 seven times; extend the auto-lock timer for a working session.
- **Fresh-index runs** build in a temp dir and delete it; `--reuse-index --data-dir` cannot write a baseline. Two fresh runs of identical code differ by ≈ 0.01–0.02 MRR (rerank/embedding nondeterminism) — a single-query gate row inside that band is noise; classify per query before ruling.
- **The gate exits before writing files.** A failed gate run leaves no `results.json`; rerun without `--gate` to get the artefacts, then rule.
- **Waiting on long runs**: `nohup … >| log 2>&1 &` (zsh noclobber) then one `until grep -q … log; do sleep 20; done` call; a Monitor on the log works for the controller. Implementers that park on a Monitor stop their turn.
- **Labels transfer.** A blind sheet is 45 minutes of Jerome's time; when a new baseline's results contain the previously labeled chunks (sections ⊇ parents), `evals/blind/transfer.py` gives the human bars with coverage and bounds instead.
- **`dup_sections@10`** keys on (file, full breadcrumb) and is driven to ~0 by dedupe-by-section; `dup_titles@10` is the cross-edition residue and is report-only.

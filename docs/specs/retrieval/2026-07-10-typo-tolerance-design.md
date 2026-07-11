# Search Typo Tolerance — Design

**Date:** 2026-07-10
**Status:** Section A + Vocabulary implemented 2026-07-10, **default-on**
(gate passed after adding general-English word protection — the design
as first specced rewrote clean queries whose words the corpus lacks).
Section A findings: docs/roadmap/2026-07-10-spell-correction-eval.md.
Section B (variant expansion) implemented 2026-07-10 behind the
**default-off** `variant_expansion` flag — the gate for default-on
**failed**: spacing variants gained nothing and clean queries regressed
(findings at the end of this doc).
**Related:** docs/roadmap/2026-07-09-search-quality-goal.md, docs/roadmap/2026-07-09-bm25-hybrid-retest.md

## Problem

`/api/search` embeds the query string verbatim (`server.py`, `collection.query`).
Typos and spacing variants therefore change retrieval:

- **True typos** ("chan mail", "chain mal"): bge-m3 tokenizes subwords, so the
  vector drifts and nearest neighbors shift. The cross-encoder reranker can't
  recover chunks that were never fetched, and it scores against the typo'd
  query too. Relevance tiers derive from raw cosine distance, so even
  correctly-retrieved results get demoted because the typo deflates similarity.
- **Spacing variants** ("chainmail" vs "chain mail"): both legitimate spellings,
  different tokenizations, different result sets.

BM25 (the default-off `hybrid` flag) does not help: exact token matching is the
worst case for typos.

## Goals

1. A misspelled query returns (approximately) the results of its corrected form.
2. Spacing variants of the same term converge on the same results.
3. Clean queries are unaffected — measured, not assumed (see Eval gate).

## Non-goals

- French / non-ASCII correction. Correction applies to ASCII tokens only,
  consistent with `_rerank_safe_for_query`. The French/OOV regime remains the
  open roadmap item it already is.
- Fuzzy lexical retrieval (char-n-gram index). Rejected: more machinery, and
  the hybrid fusion route just tested NO-GO on aggregate metrics.
- UI "did you mean" affordances beyond surfacing the correction in the
  response. The UI can adopt `corrected_query` later if wanted.

## Design

Two cooperating mechanisms, both driven by a library-derived vocabulary:

- **A. Spell correction** — rewrite out-of-vocabulary tokens to the closest
  in-vocabulary term before embedding.
- **B. Variant expansion** — when vocab evidence says a token can be split
  ("chainmail" → "chain mail") or a pair joined ("chain mail" → "chainmail"),
  search both forms and fuse the rankings.

### Vocabulary

A term → frequency map over the indexed chunks:

- Tokens from the same `[A-Za-z0-9]+` regex the lexical index uses, lowercased,
  **unstemmed** (the FTS5 index is porter-stemmed — wrong surface forms for a
  spell dictionary, so this is a separate pass, not a reuse of `LexicalIndex`).
- Built lazily on first use from a batched `collection.get` scan; cached and
  rebuilt when `collection.count()` changes — the exact `lexical_cache`
  pattern at `server.py` (`_get_lexical_index`). If the build proves slow at
  real library scale (gate: noticeably delaying the first search, >~2s),
  fall back to persisting term counts in the data dir — not built now.
- A token counts as **in-vocab** only at frequency ≥ `MIN_VOCAB_FREQ`
  (start 3, tune during eval). PDF extraction produces junk terms
  ("byweapon"); a low-frequency artifact must neither block correction of a
  real typo nor become a correction target.

### A. Spell correction

- Dependency: `symspellpy` (pure Python, MIT, no ML — consistent with the
  sidecar dependency policy). Dictionary loaded from the vocabulary above.
- Correct **only OOV tokens** (frequency < `MIN_VOCAB_FREQ`). In-vocab tokens
  are never rewritten — protects proper nouns ("Tiamat", "Strahd") and rare
  but real terms.
- Skip tokens containing digits ("5e", "d20", "1d6"), tokens of length ≤ 2,
  and non-ASCII tokens.
- Max edit distance 2; 1 for tokens of length ≤ 4.
- The corrected query is reconstructed by replacing the token spans in the
  original string, leaving everything else (punctuation, casing of untouched
  tokens) intact.
- Downstream consumers of the query text use the **corrected** form: the dense
  embed, the reranker, `detect_systems_in_query`, and the BM25 side when
  `hybrid` is on.

### B. Variant expansion

Applied to the corrected query, direct vocab checks (no symspell):

- **Join:** adjacent token pair (a, b) where the concatenation `ab` is
  in-vocab → variant query with the joined form.
- **Split:** token t (in-vocab or not) that can be written t = a + b with both
  parts in-vocab → variant query with the split form. If several boundaries
  qualify, take the one maximizing `min(freq(a), freq(b))`.
- Cap: at most 2 variant queries beyond the primary (realistic queries have
  at most one or two candidate spots; the cap bounds the fan-out).

### Query flow

1. Correct the query (A). If nothing changed and no variants exist (B), the
   request follows today's single-query path — zero overhead for the common
   case.
2. Otherwise issue one Chroma call with `query_texts=[primary, *variants]`
   (multi-query is a single round-trip; each ranking over-fetched ×10 as
   today).
3. Fuse the per-variant rankings with the existing `rrf_fuse`, exactly as the
   hybrid path does — set `ordering_scores` from the fused RRF scores so the
   soft-boost path weighs the right scale. When `hybrid` is on, the BM25
   ranking joins the same `rrf_fuse` call as one more ranking.
4. A fused candidate's reported distance is the **minimum** across the variant
   rankings it appeared in (every candidate has a real cosine distance from at
   least one variant — no sentinels needed, unlike BM25-only candidates).
5. The fused pool feeds the unchanged boost → rerank → dedupe-by-parent
   pipeline. The reranker scores against the corrected primary query.

### API surface

- `SearchRequest.spell_correction: bool = True` — mirrors `rerank`/`hybrid`;
  the off-switch exists for eval ablation and as an escape hatch.
- Response gains `corrected_query: str | null` (null when untouched) and a
  note in the existing `message` channel (the `filter_notes` mechanism):
  `Query corrected to "chain mail".` — this is what MCP agents read.
- No MCP tool-schema change: the correction note flows through `message`.

### Lifecycle & packaging

- Vocabulary and symspell dictionary rebuild together on chunk-count change
  (reindex/delete), same trigger as the lexical index.
- `symspellpy` added to `pyproject.toml`; pure Python, so no PyInstaller spec
  changes expected beyond the dependency (verify in the build).

## Eval plan and GO/NO-GO gate

1. **New eval category `typo_variant`** in `sidecar/evals/queries.yaml`:
   variants of ~10–12 locked queries — one character-deletion typo, one
   adjacent transposition, one spacing variant each — keeping the original
   `source`/`pages`/`answer` anchors. The locked originals stay untouched.
2. **Baseline first:** run the eval on the typo set *before* the fix to
   quantify today's degradation vs. the clean originals.
3. **Gate for default-on:**
   - Typo set closes most of the gap to its clean counterparts (target:
     ≥ half the nDCG/MRR gap, judged per-category like the BM25 re-test).
   - Full clean-query suite does not regress vs. the 2026-07-09 baseline
     (within noise). Variant expansion triggers on clean queries too
     ("chainmail" splits), so this is a real risk to measure, not a formality.
   - If the gate fails, ship default-off behind the flag and record findings,
     as with the BM25 re-test.
4. `run_eval.py` gains `--no-spell-correction` (pattern of `--no-rerank`) and
   records the setting in the baseline metadata.

## Testing

- Unit: vocabulary build (frequencies, junk-term thresholding), OOV detection,
  correction (typos corrected; proper nouns, digit tokens, short tokens, and
  non-ASCII untouched), split/join variant generation, query-span
  reconstruction.
- Endpoint: typo'd query returns the corrected query's parents; `message` and
  `corrected_query` populated; `spell_correction: false` bypasses everything;
  composition with `hybrid: true`.
- Eval: baseline + post-implementation runs per the gate above.

## Risks / open questions

- **Vocab build cost at scale** — mitigated by the cache pattern and the
  measured fallback to persistence (explicitly deferred).
- **Correction to OCR junk** — mitigated by `MIN_VOCAB_FREQ`; tune with eval.
- **Clean-query regression from variant expansion** — the eval gate exists
  precisely for this; the flag is the fallback. *(This is exactly how it
  played out — see below.)*

## Section B eval findings (2026-07-10): NO-GO for default-on

Implemented as designed — `SpellCorrector.expand()` split/join over the
shared vocabulary (plus a ≥3-char guard on split parts: possessive
tokenization puts a high-frequency bare "s" in every vocabulary, which
would otherwise split "sword" into "s word"), multi-query Chroma call,
`rrf_fuse` across the variant rankings with minimum distance reported,
BM25 joining the same fusion under `hybrid`. Gate run against the post-A
baseline with 5 new `variant: spacing` eval queries (both directions;
the 5 of 10 locked originals with a natural compound term). Baselines:
`2026-07-10-pre-variant-expansion.*` (A only) vs
`2026-07-10-variant-expansion.*` (A + B).

| subset | nDCG@10 | MRR@5 | recall@10 |
|---|---|---|---|
| spacing variants (5) | 0.826 → 0.826 | 0.767 → 0.767 | 1.000 → 1.000 |
| misspellings (20) | 0.611 → 0.598 | 0.525 → 0.508 | 0.850 → 0.850 |
| clean suite (40) | 0.644 → 0.641 | 0.584 → 0.580 | 0.850 → 0.850 |

- **There was almost no gap to close.** Pre-B, the spacing set already
  sat at 0.826 nDCG vs 0.852 for its clean originals (+0.026): bge-m3's
  subword tokenization absorbs spacing variance on its own ("chainmail"
  and "chain mail" share subword pieces; recall@10 was already 1.000).
  The premise that spacing variants materially diverge — true for BM25 —
  does not hold for the dense retriever that actually serves results.
- **Expansion moved no spacing query by any metric.** Every one of the
  5 spacing queries scored identically with and without fusion.
- **Clean queries regressed.** "Fireball damage and area of effect"
  0.631 → 0.500 nDCG: its own "Fire ball" split variant fused
  lower-quality neighbors above the answer chunk. "Fireball damage in
  5E SRD" 0.356 → 0.333. One small gain ("Goblin attack damage",
  +0.014). Net clean prose −0.012 nDCG / −0.015 MRR — deterministic
  per-query regressions, not noise.
- **Misspellings regressed too** (−0.013 nDCG / −0.017 MRR): expansion
  runs after correction, and RRF gives the variant ranking equal say —
  diluting rankings the corrected primary already had right.

**Re-test at production page size (same day):** after the harness moved
to the UI's page size (`n_results=25`, the #340 lesson), the gate was
re-run — `*-p25` baselines. NO-GO confirmed and slightly amplified:
spacing variants still moved zero on every metric; misspellings
regressed further (−0.031 nDCG, and recall@10 −0.050 — with 250-deep
rankings the RRF dilution now pushes answers out of the top 10, not
just down it). The clean suite nets +0.003 nDCG but that is two
offsetting single-query moves ("Goblin attack damage" +0.245, the same
"Fireball" −0.131), not a signal.

**Decision:** section A stays default-on, untouched. Section B ships
behind `variant_expansion` (default **off**, independent of
`spell_correction`, same vocabulary; `--variant-expansion` in
`run_eval`). The spacing eval queries stay in `typo_variant` so any
re-test measures the same thing. A re-test would only be warranted with
a retriever whose tokenization does not already absorb spacing (e.g. if
the BM25 hybrid regime is ever revisited — there the lexical side is
exactly where spacing variants diverge).

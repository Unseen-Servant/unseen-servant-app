# Spell correction (typo-tolerance section A) — NO-GO for default-on (flag retained)

**Date:** 2026-07-10
**Context:** Implements section A + Vocabulary of the
[typo-tolerance design](../specs/retrieval/2026-07-10-typo-tolerance-design.md):
out-of-vocabulary query tokens are rewritten to the closest library term
(symspellpy over a library-derived frequency vocabulary) before the dense
embed, reranker, system detection, and BM25 side see the query. Section B
(split/join variant expansion) is **not** built; the eval's `typo_variant`
category accordingly covers misspellings only (one character-deletion and
one adjacent-transposition variant for each of 10 locked queries — spacing
variants come with section B).

## What was built

- [sidecar/spelling.py](../../sidecar/spelling.py) — term→frequency
  vocabulary over the heading-prepended chunks (lowercased, unstemmed,
  `MIN_VOCAB_FREQ = 3`) + a symspellpy corrector: OOV tokens only, max
  edit distance 2 (1 at length ≤ 4), digit/short/non-ASCII tokens and the
  whole query when non-ASCII skipped, span-splicing reconstruction.
- A default-off `spell_correction` flag on `/api/search`; the corrected
  form drives the dense embed, reranker, `detect_systems_in_query`, and
  the BM25 side under `hybrid`. Response gains `corrected_query` and a
  `Query corrected to "…".` note in `message`. Vocabulary rebuilds on
  chunk-count change (lexical-index cache pattern).
- `--spell-correction` on `evals.run_eval` (mirrors `--hybrid`), setting
  recorded in baseline metadata; 20 pre-registered `typo_variant` queries.
- Dependency: `symspellpy==6.9.0` (brings `editdistpy`, a compiled
  extension — verify in the next release build per CI policy).

Baselines: `sidecar/evals/baselines/2026-07-10-pre-spellfix.*` (correction
off; clean categories reproduce the 2026-07-09 baseline to the digit) and
`2026-07-10-spellfix.*` (correction on). Rerank on in both.

## Results

| set | n | nDCG@10 | | MRR@5 | | recall@10 | |
|---|---|---|---|---|---|---|---|
| | | off | on | off | on | off | on |
| typo_variant | 20 | 0.444 | **0.653** | 0.342 | **0.558** | 0.700 | **0.900** |
| …their clean originals | 10 | 0.731 | 0.731 | 0.633 | 0.633 | 1.000 | 1.000 |
| cross_system (clean) | 10 | 0.580 | 0.537 | 0.550 | **0.458** | 0.700 | 0.800 |
| other clean categories | 30 | — | unchanged | — | unchanged | — | unchanged |

- **The typo-side gate passes decisively.** The typo set closes ~73% of
  the nDCG gap and ~74% of the MRR gap to its clean counterparts
  (target: ≥ half), and recall@10 recovers 0.700 → 0.900.
- **The clean-side gate fails.** 8 of 40 clean queries were rewritten;
  cross_system regressed −0.043 nDCG / −0.092 MRR — far beyond noise in a
  deterministic pipeline. The gate's "strict no-op on clean queries" does
  not hold.

## Why clean queries get rewritten

Two failure modes, both structural, with corpus frequencies in evidence:

1. **Query vocabulary ≠ corpus vocabulary.** Real query words the books
   never (or rarely) print are OOV and become correction fodder:
   `stats` (freq 0) → `starts` (128), `Black Flag` → `Black Flat`
   (`flag` = 1, `flat` = 18 — the rewrite also defeats the game-system
   soft-boost for Black Flag queries), `percentages` (1) →
   `percentage` (3), `calculation` (1) → `calculating` (11). No
   `MIN_VOCAB_FREQ` value fixes this: a threshold cannot protect a real
   word with corpus frequency 0, and lowering it re-admits OCR junk.
2. **Frequency tie-breaks favor ubiquitous words.** At equal edit
   distance symspell picks the higher count, so function words drown
   domain terms even on the typo set: `thif` → `this` (3485 vs `thief`
   184), `theif` → `their` (851), `figher` → `higher` (730 vs `fighter`
   402), `chan` → `can` (7334 vs `chain` 109). The typo-set gains above
   survive these misfires (the reranker often rescues the remaining
   correct tokens), but they cap the ceiling.

## Recommendation: NO-GO for default-on. Keep the flag.

Do not enable `spell_correction` by default; production behavior is
unchanged (the correction-off run reproduces the 2026-07-09 baseline to
the digit). The flag, module, and `typo_variant` eval set stay as the
measurement instrument, per the BM25 re-test precedent.

What would change the verdict — both fixes look tractable and are
prerequisites for a re-test:

1. **Protect real English.** Treat a token as in-vocab if it is either
   library-vocab (≥ threshold) or in a general-English frequency list
   (symspellpy ships `frequency_dictionary_en_82_765.txt`). This single
   change would have prevented all 8 clean-query rewrites measured here.
2. **Fix the tie-break.** At equal edit distance, prefer the
   library-distinctive candidate rather than raw count (e.g. down-weight
   general-English stopwords as correction targets, or require the
   winner to beat alternatives by distance, not count).

Section B (variant expansion) remains unimplemented; its split/join
mechanics and the spacing-variant eval queries should land together with
the re-test.

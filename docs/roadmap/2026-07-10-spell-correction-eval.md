# Spell correction (typo-tolerance section A) — GO for default-on, after an English-guard fix

**Date:** 2026-07-10
**Context:** Implements section A + Vocabulary of the
[typo-tolerance design](../retrieval/2026-07-10-typo-tolerance-design.md):
out-of-vocabulary query tokens are rewritten to the closest library term
(symspellpy over a library-derived frequency vocabulary) before the dense
embed, reranker, system detection, and BM25 side see the query. Section B
(split/join variant expansion) is **not** built; the eval's `typo_variant`
category accordingly covers misspellings only (one character-deletion and
one adjacent-transposition variant for each of 10 locked queries — spacing
variants come with section B).

The gate ran twice: the design as specced **failed** the clean-query
no-op requirement (round 1), a general-English protection fixed it, and
the re-run **passed** (round 2). Both rounds are recorded below.

## What was built

- [sidecar/spelling.py](../../sidecar/spelling.py) — term→frequency
  vocabulary over the heading-prepended chunks (lowercased, unstemmed,
  `MIN_VOCAB_FREQ = 3`) + a symspellpy corrector: OOV tokens only, max
  edit distance 2 (1 at length ≤ 4), digit/short/non-ASCII tokens and the
  whole query when non-ASCII skipped, span-splicing reconstruction, and —
  added after round 1 — **general-English protection**: a token found in
  symspellpy's bundled `frequency_dictionary_en_82_765.txt` is never
  rewritten (protection only; correction targets remain library terms).
- A default-on `spell_correction` flag on `/api/search`; the corrected
  form drives the dense embed, reranker, `detect_systems_in_query`, and
  the BM25 side under `hybrid`. Response gains `corrected_query` and a
  `Query corrected to "…".` note in `message`. Vocabulary rebuilds on
  chunk-count change (lexical-index cache pattern).
- `--no-spell-correction` on `evals.run_eval` (pattern of `--no-rerank`),
  setting recorded in baseline metadata; 20 pre-registered `typo_variant`
  queries with `variant_of`/`variant` fields.
- Dependency: `symspellpy==6.9.0` (brings `editdistpy`, a compiled
  extension — verify in the next release build per CI policy).

Baselines (rerank on in all):

- `2026-07-10-pre-spellfix.*` — correction off, run **before**
  implementation; clean categories reproduce the 2026-07-09 baseline to
  the digit.
- `2026-07-10-spellfix.*` — round 1, correction on, no English guard.
- `2026-07-10-spellfix-en-guard.*` — round 2, correction on + guard.

## Results

| set | n | nDCG@10 | | | MRR@5 | | | recall@10 | | |
|---|---|---|---|---|---|---|---|---|---|---|
| | | off | r1 | r2 | off | r1 | r2 | off | r1 | r2 |
| typo_variant | 20 | 0.444 | 0.653 | **0.611** | 0.342 | 0.558 | **0.525** | 0.700 | 0.900 | **0.850** |
| …their clean originals | 10 | 0.731 | 0.731 | 0.731 | 0.633 | 0.633 | 0.633 | 1.000 | 1.000 | 1.000 |
| cross_system (clean) | 10 | 0.580 | 0.537 | **0.580** | 0.550 | **0.458** | **0.550** | 0.700 | 0.800 | 0.700 |
| other clean categories | 30 | — | unchanged | identical | — | unchanged | identical | — | unchanged | identical |

- **Round 1 failed the clean-side gate.** 8 of 40 clean queries were
  rewritten; cross_system regressed −0.043 nDCG / −0.092 MRR. Two
  structural causes, with corpus frequencies in evidence:
  1. *Query vocabulary ≠ corpus vocabulary* — real query words the books
     never print are OOV and became correction fodder: `stats` (freq 0)
     → `starts` (128), `Black Flag` → `Black Flat` (`flag` = 1,
     `flat` = 18 — also defeating the game-system soft-boost),
     `percentages` (1) → `percentage` (3), `calculation` (1) →
     `calculating` (11). No `MIN_VOCAB_FREQ` value fixes a real word
     with corpus frequency 0.
  2. *Frequency tie-breaks favor ubiquitous words* — at equal edit
     distance symspell picks the higher count: `thif` → `this` (3485 vs
     `thief` 184), `figher` → `higher` (730 vs `fighter` 402).
- **Round 2 (English guard) passes both gates.**
  - *Clean suite is a strict no-op, measured:* zero of 40 clean queries
    corrected; every clean category reproduces the correction-off
    baseline **to the digit**.
  - *Typo set closes ≥ half the gap:* 58% of nDCG (0.444 → 0.611 vs
    clean 0.731) and 63% of MRR (0.342 → 0.525 vs clean 0.633);
    recall@10 0.700 → 0.850.
  - The guard costs some typo-side ceiling vs round 1 (−0.042 nDCG):
    `chan` and `chian` are themselves dictionary words (proper name /
    Chian), so the chain-mail variants are no longer corrected.
    Protection of real words wins that trade by design.

## Decision: GO — `spell_correction` defaults on

Clean behavior is provably unchanged and misspelled queries recover most
of their lost quality. The off-switch stays for eval ablation and as an
escape hatch.

Known limits, for the section-B follow-up:

1. **Tie-break misfires persist** (`thif` → `this`, `figher` →
   `higher`): the English guard protects clean queries but at equal edit
   distance a typo can still land on a ubiquitous word instead of the
   domain term. A library-distinctive tie-break would raise the typo-set
   ceiling (round 1 showed ~0.65 nDCG is reachable).
2. **English-word typos are uncorrectable by design** — a typo that hits
   a real dictionary word ("chan mail", "form"/"from") passes through.
3. **Vocab build cost at scale** — unmeasured beyond the eval corpus;
   the design's persistence fallback stays deferred until a real library
   shows the first search stalling.
4. Section B (variant expansion) remains unimplemented; its split/join
   mechanics and spacing-variant eval queries should land together.

# Retrieval baseline — v3 — rerank-srcfilter

Date: 2026-08-19
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.592     0.624      0.667      0.708      0.708          23956           0.042
single                24    0.460     0.501      0.542      0.583      0.625          20519           0.458
uncued                20    0.825     0.860      0.950      0.950      1.000          18497           0.200
all                   68    0.614     0.650      0.706      0.735      0.765          21137           0.235
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000          26648           0.000
exact_name            18    0.528     0.583      0.667      0.667      0.722          21950           0.667
prose_rule            34    0.703     0.730      0.765      0.824      0.853          19318           0.088
table_lookup          12    0.694     0.740      0.833      0.833      0.833          23235           0.083
all                   68    0.614     0.650      0.706      0.735      0.765          21137           0.235
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.625     0.664      0.706      0.765      0.794          20996           0.235
nl                    34    0.603     0.636      0.706      0.706      0.735          21279           0.235
all                   68    0.614     0.650      0.706      0.735      0.765          21137           0.235
```

Search latency over 68 queries: mean 258ms, p50 244ms, p95 361ms

Misses: q001, q002, q004, q005, q006, q010, q016, q041, q042, q023, q024, q025, q045, q046, q047, q050

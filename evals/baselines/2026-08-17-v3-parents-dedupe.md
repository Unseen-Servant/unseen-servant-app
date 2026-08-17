# Retrieval baseline — v3 — parents-dedupe

Date: 2026-08-17
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=False spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.359     0.417      0.458      0.542      0.583          22728           0.042
single                24    0.418     0.488      0.458      0.667      0.708          22711           0.542
uncued                20    0.883     0.883      1.000      1.000      1.000          20587           0.200
all                   68    0.534     0.579      0.618      0.721      0.750          22092           0.265
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000          25990           0.250
exact_name            18    0.481     0.505      0.556      0.667      0.667          23923           0.500
prose_rule            34    0.556     0.620      0.676      0.794      0.824          20969           0.118
table_lookup          12    0.729     0.767      0.750      0.833      0.917          21228           0.333
all                   68    0.534     0.579      0.618      0.721      0.750          22092           0.265
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.548     0.573      0.618      0.735      0.735          21380           0.294
nl                    34    0.521     0.585      0.618      0.706      0.765          22804           0.235
all                   68    0.534     0.579      0.618      0.721      0.750          22092           0.265
```

Search latency over 68 queries: mean 47ms, p50 43ms, p95 78ms

Misses: q005, q006, q007, q008, q016, q041, q042, q021, q023, q024, q025, q026, q045, q046, q047, q050

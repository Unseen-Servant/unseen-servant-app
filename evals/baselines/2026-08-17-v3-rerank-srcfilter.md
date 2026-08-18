# Retrieval baseline — v3 — rerank-srcfilter

Date: 2026-08-17
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.675     0.696      0.708      0.750      0.750          24921           0.000
single                24    0.438     0.482      0.458      0.458      0.583          22880           0.542
uncued                20    0.775     0.855      0.950      0.950      1.000          20636           0.150
all                   68    0.621     0.667      0.691      0.706      0.765          22940           0.235
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000          33507           0.000
exact_name            18    0.611     0.645      0.667      0.667      0.722          24429           0.722
prose_rule            34    0.697     0.731      0.765      0.794      0.824          20105           0.059
table_lookup          12    0.625     0.741      0.750      0.750      0.917          25218           0.083
all                   68    0.621     0.667      0.691      0.706      0.765          22940           0.235
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.624     0.666      0.706      0.735      0.765          22804           0.235
nl                    34    0.618     0.669      0.676      0.676      0.765          23076           0.235
all                   68    0.621     0.667      0.691      0.706      0.765          22940           0.235
```

Search latency over 68 queries: mean 293ms, p50 277ms, p95 428ms

Misses: q001, q002, q003, q004, q005, q006, q010, q041, q042, q023, q024, q045, q046, q047, q050

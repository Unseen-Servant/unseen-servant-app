# Retrieval baseline — v3 — system-boost

Date: 2026-08-17
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.576     0.617      0.667      0.667      0.708          24984           0.000
single                24    0.477     0.539      0.625      0.708      0.750          22900           0.500
uncued                20    0.850     0.857      0.950      0.950      1.000          20864           0.150
all                   68    0.622     0.660      0.735      0.765      0.809          23037           0.221
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000          27080           0.250
exact_name            18    0.630     0.623      0.722      0.722      0.722          25634           0.444
prose_rule            34    0.621     0.682      0.765      0.824      0.882          21404           0.059
table_lookup          12    0.819     0.874      0.917      0.917      1.000          22420           0.333
all                   68    0.622     0.660      0.735      0.765      0.809          23037           0.221
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.625     0.658      0.735      0.765      0.794          22858           0.265
nl                    34    0.619     0.662      0.735      0.765      0.824          23216           0.176
all                   68    0.622     0.660      0.735      0.765      0.809          23037           0.221
```

Search latency over 68 queries: mean 60ms, p50 55ms, p95 92ms

Misses: q005, q006, q041, q042, q023, q024, q025, q045, q046, q047, q050

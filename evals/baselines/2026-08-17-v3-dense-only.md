# Retrieval baseline — v3 — dense-only

Date: 2026-08-17
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=False spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.060     0.118      0.042      0.125      0.250           4484           1.208
single                24    0.094     0.137      0.083      0.125      0.250           4538           2.708
uncued                20    0.377     0.516      0.450      0.700      0.850           4621           1.800
all                   68    0.165     0.242      0.176      0.294      0.426           4543           1.912
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000           5687           4.750
exact_name            18    0.275     0.345      0.278      0.389      0.556           4866           1.833
prose_rule            34    0.163     0.249      0.176      0.324      0.441           4530           1.412
table_lookup          12    0.062     0.148      0.083      0.167      0.333           3718           2.500
all                   68    0.165     0.242      0.176      0.294      0.426           4543           1.912
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.138     0.205      0.118      0.265      0.382           3295           1.853
nl                    34    0.192     0.279      0.235      0.324      0.471           5792           1.971
all                   68    0.165     0.242      0.176      0.294      0.426           4543           1.912
```

Search latency over 68 queries: mean 44ms, p50 42ms, p95 60ms

Misses: q001, q002, q003, q004, q005, q006, q007, q008, q009, q010, q011, q015, q016, q037, q038, q041, q042, q017, q019, q020, q021, q023, q024, q045, q046, q047, q050, q051, q052

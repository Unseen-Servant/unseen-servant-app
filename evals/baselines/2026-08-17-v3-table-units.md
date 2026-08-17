# Retrieval baseline — v3 — table-units

Date: 2026-08-17
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=False spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.283     0.345      0.333      0.417      0.500           6922           3.958
single                24    0.238     0.275      0.333      0.375      0.375           6755           4.292
uncued                20    0.768     0.800      0.850      1.000      1.000           7182           3.000
all                   68    0.410     0.454      0.485      0.574      0.603           6939           3.794
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000           8059           4.500
exact_name            18    0.412     0.452      0.500      0.556      0.611           6870           5.000
prose_rule            34    0.380     0.454      0.471      0.618      0.647           7680           2.735
table_lookup          12    0.625     0.607      0.667      0.667      0.667           4572           4.750
all                   68    0.410     0.454      0.485      0.574      0.603           6939           3.794
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.430     0.464      0.500      0.559      0.588           6257           3.735
nl                    34    0.389     0.444      0.471      0.588      0.618           7622           3.853
all                   68    0.410     0.454      0.485      0.574      0.603           6939           3.794
```

Search latency over 68 queries: mean 58ms, p50 54ms, p95 96ms

Misses: q001, q002, q005, q006, q007, q008, q009, q010, q015, q016, q037, q038, q041, q042, q021, q023, q024, q045, q046, q047, q050, q051, q052

# Retrieval baseline — v3 — heading-prepend

Date: 2026-08-17
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=False spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cued                  24    0.258     0.329      0.250      0.375      0.500           7210           3.417
single                24    0.212     0.269      0.333      0.375      0.417           7114           3.833
uncued                20    0.695     0.753      0.800      1.000      1.000           7472           2.550
all                   68    0.370     0.432      0.441      0.559      0.618           7253           3.309
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
cross_page             4    0.000     0.000      0.000      0.000      0.000           7853           4.750
exact_name            18    0.435     0.459      0.444      0.556      0.611           7390           4.500
prose_rule            34    0.382     0.456      0.471      0.618      0.647           7497           2.529
table_lookup          12    0.364     0.469      0.500      0.583      0.750           6158           3.250
all                   68    0.370     0.432      0.441      0.559      0.618           7253           3.309
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10
-----------------------------------------------------------------------------------------------------------
keyword               34    0.403     0.452      0.471      0.559      0.618           6252           2.971
nl                    34    0.338     0.413      0.412      0.559      0.618           8255           3.647
all                   68    0.370     0.432      0.441      0.559      0.618           7253           3.309
```

Search latency over 68 queries: mean 40ms, p50 38ms, p95 55ms

Misses: q001, q002, q005, q006, q007, q008, q015, q016, q037, q038, q041, q042, q021, q023, q024, q045, q046, q047, q050, q051, q052

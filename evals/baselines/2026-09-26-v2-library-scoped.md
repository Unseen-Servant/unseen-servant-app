# Retrieval baseline — v2 — library-scoped

Date: 2026-09-26
Corpus docs: db_adventures, db_bestiary, db_rulebook, osric_2e, srd_5_1
Queries: 34 (17 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
collection            18    0.972     0.945      1.000      1.000      1.000          72196           0.000         0.056        0.333
cued                  12    0.635     0.724      0.833      1.000      1.000          70479           0.000         0.167        0.417
uncued                 4    0.875     0.881      1.000      1.000      1.000          73802           0.000         2.000        0.500
all                   34    0.842     0.860      0.941      1.000      1.000          71779           0.000         0.324        0.382
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
exact_name            12    0.812     0.829      0.917      1.000      1.000          62176           0.000         0.667        0.583
prose_rule            18    0.826     0.849      0.944      1.000      1.000          76819           0.000         0.167        0.333
table_lookup           4    1.000     1.000      1.000      1.000      1.000          77905           0.000         0.000        0.000
all                   34    0.842     0.860      0.941      1.000      1.000          71779           0.000         0.324        0.382
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
keyword               17    0.843     0.866      1.000      1.000      1.000          71651           0.000         0.294        0.412
nl                    17    0.840     0.854      0.882      1.000      1.000          71906           0.000         0.353        0.353
all                   34    0.842     0.860      0.941      1.000      1.000          71779           0.000         0.324        0.382
```

Search latency over 34 queries: mean 297ms, p50 285ms, p95 490ms

Misses: none

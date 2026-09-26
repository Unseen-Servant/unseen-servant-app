# Retrieval baseline — v2 — library-cue-strip

Date: 2026-09-26
Corpus docs: db_adventures, db_bestiary, db_rulebook, osric_2e, srd_5_1
Queries: 40 (20 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
collection            18    0.972     0.945      1.000      1.000      1.000          72196           0.000         0.056        0.333
cued                  18    0.972     0.963      1.000      1.000      1.000          70971           0.000         0.000        0.500
uncued                 4    0.875     0.881      1.000      1.000      1.000          73802           0.000         2.000        0.500
all                   40    0.963     0.947      1.000      1.000      1.000          71805           0.000         0.225        0.425
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
exact_name            16    0.938     0.913      1.000      1.000      1.000          62471           0.000         0.500        0.688
prose_rule            18    0.972     0.960      1.000      1.000      1.000          80386           0.000         0.056        0.222
table_lookup           6    1.000     1.000      1.000      1.000      1.000          70953           0.000         0.000        0.333
all                   40    0.963     0.947      1.000      1.000      1.000          71805           0.000         0.225        0.425
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
keyword               20    0.950     0.941      1.000      1.000      1.000          70969           0.000         0.250        0.450
nl                    20    0.975     0.953      1.000      1.000      1.000          72641           0.000         0.200        0.400
all                   40    0.963     0.947      1.000      1.000      1.000          71805           0.000         0.225        0.425
```

Search latency over 40 queries: mean 381ms, p50 356ms, p95 634ms

Misses: none

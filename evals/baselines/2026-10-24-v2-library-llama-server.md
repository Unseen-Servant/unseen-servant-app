# Retrieval baseline — v2 — library-llama-server

Date: 2026-10-24
Corpus docs: db_adventures, db_bestiary, db_rulebook, osric_2e, srd_5_1
Queries: 40 (20 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
collection            18    0.972     0.943      1.000      1.000      1.000          73645           0.000         0.056        0.333
cued                  18    0.907     0.920      1.000      1.000      1.000          66229           0.000         0.222        0.556
uncued                 4    1.000     0.930      1.000      1.000      1.000          72765           0.000         2.000        0.250
all                   40    0.946     0.932      1.000      1.000      1.000          70220           0.000         0.325        0.425
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
exact_name            16    0.927     0.898      1.000      1.000      1.000          63722           0.000         0.500        0.625
prose_rule            18    0.972     0.960      1.000      1.000      1.000          74699           0.000         0.167        0.278
table_lookup           6    0.917     0.938      1.000      1.000      1.000          74110           0.000         0.333        0.333
all                   40    0.946     0.932      1.000      1.000      1.000          70220           0.000         0.325        0.425
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
keyword               20    0.950     0.932      1.000      1.000      1.000          69394           0.000         0.350        0.450
nl                    20    0.942     0.931      1.000      1.000      1.000          71045           0.000         0.300        0.400
all                   40    0.946     0.932      1.000      1.000      1.000          70220           0.000         0.325        0.425
```

Search latency over 40 queries: mean 301ms, p50 269ms, p95 495ms

Misses: none

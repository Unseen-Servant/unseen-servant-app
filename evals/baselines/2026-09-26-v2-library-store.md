# Retrieval baseline — v2 — library-store

Date: 2026-09-26
Corpus docs: bfrpg_4e, black_hack_1e, cairn_1e, osric_2e, srd_5_1, srd_5_2_1, yze_srd
Queries: 68 (34 pairs)  |  n_results: 25
Knobs: rerank=True hybrid=True spell_correction=True variant_expansion=False

## By scope
```
scope            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
cued                  24    0.750     0.784      0.833      0.833      0.875          48169           0.083         0.042        0.750
single                24    0.948     0.939      0.958      1.000      1.000          42162           0.125         0.000        0.833
uncued                20    0.942     0.912      1.000      1.000      1.000          40624           0.250         1.450        0.850
all                   68    0.876     0.877      0.926      0.941      0.956          43830           0.147         0.441        0.809
```

## By category
```
category         queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
cross_page             4    1.000     1.000      1.000      1.000      1.000          49636           0.000         0.000        0.500
exact_name            18    1.000     0.972      1.000      1.000      1.000          43019           0.056         0.556        0.889
prose_rule            34    0.819     0.821      0.882      0.882      0.912          40555           0.118         0.529        0.824
table_lookup          12    0.812     0.850      0.917      1.000      1.000          52391           0.417         0.167        0.750
all                   68    0.876     0.877      0.926      0.941      0.956          43830           0.147         0.441        0.809
```

## By style
```
style            queries    mrr@5   ndcg@10   recall@3   recall@5  recall@10  payload_chars dup_sections@10 dup_titles@10  top3_fit@8k
--------------------------------------------------------------------------------------------------------------------------------------
keyword               34    0.912     0.908      0.941      0.941      0.971          43607           0.176         0.529        0.882
nl                    34    0.841     0.846      0.912      0.941      0.941          44053           0.118         0.353        0.735
all                   68    0.876     0.877      0.926      0.941      0.956          43830           0.147         0.441        0.809
```

Search latency over 68 queries: mean 376ms, p50 375ms, p95 470ms

Misses: q023, q024

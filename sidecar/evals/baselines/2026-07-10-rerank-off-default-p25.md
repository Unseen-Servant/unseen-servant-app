# Retrieval eval baseline — 2026-07-11T02:46:15+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 65 (graded on the specific answer chunk)
Rerank: off
Retrieval: dense
Spell correction: on
Variant expansion: off
Page size: 25 (metrics graded @10)
search latency over 65 queries: mean 208ms, median 204ms, p95 261ms (in-process, post-warmup)

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.712         0.611         0.333         0.333         1.000         1.000
cross_system        10         0.759         0.750         0.160         0.090         0.800         0.800
prose               11         0.558         0.495         0.145         0.091         0.636         0.727
stat_block           6         1.000         1.000         0.200         0.100         1.000         1.000
table               10         0.724         0.700         0.200         0.120         0.800         0.900
typo_variant        25         0.727         0.676         0.184         0.100         0.840         0.880
all                 65         0.727         0.687         0.185         0.111         0.815         0.862
```

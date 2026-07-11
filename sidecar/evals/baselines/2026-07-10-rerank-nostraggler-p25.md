# Retrieval eval baseline — 2026-07-11T02:37:40+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 65 (graded on the specific answer chunk)
Rerank: on
Retrieval: dense
Spell correction: on
Variant expansion: off
Page size: 25 (metrics graded @10)
search latency over 65 queries: mean 1297ms, median 1297ms, p95 1750ms (in-process, post-warmup)

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.877         0.833         0.600         0.400         1.000         1.000
cross_system        10         0.588         0.500         0.120         0.090         0.600         0.800
prose               11         0.459         0.321         0.164         0.091         0.727         0.818
stat_block           6         0.968         1.000         0.200         0.117         1.000         1.000
table               10         0.648         0.583         0.180         0.140         0.800         0.900
typo_variant        25         0.668         0.573         0.192         0.100         0.880         0.920
all                 65         0.655         0.572         0.194         0.118         0.815         0.892
```

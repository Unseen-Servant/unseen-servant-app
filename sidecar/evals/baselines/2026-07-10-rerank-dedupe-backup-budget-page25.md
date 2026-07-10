# Retrieval eval baseline — 2026-07-10T16:39:17+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 65 (graded on the specific answer chunk)
Rerank: on
Retrieval: dense
Spell correction: on
Variant expansion: off
Page size: 25 (metrics graded @10)
search latency over 65 queries: mean 1919ms, median 1985ms, p95 2572ms (in-process, post-warmup)

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.833         0.778         0.600         0.400         1.000         1.000
cross_system        10         0.544         0.470         0.120         0.080         0.600         0.700
prose               11         0.444         0.288         0.145         0.091         0.636         0.818
stat_block           6         0.966         1.000         0.200         0.117         1.000         1.000
table               10         0.614         0.537         0.180         0.130         0.800         0.900
typo_variant        25         0.661         0.555         0.200         0.104         0.920         0.960
all                 65         0.635         0.545         0.194         0.117         0.815         0.892
```

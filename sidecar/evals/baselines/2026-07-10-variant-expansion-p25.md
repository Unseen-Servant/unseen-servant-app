# Retrieval eval baseline — 2026-07-11T01:39:35+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 65 (graded on the specific answer chunk)
Rerank: on
Retrieval: dense
Spell correction: on
Variant expansion: on
Page size: 25 (metrics graded @10)
search latency over 65 queries: mean 1321ms, median 1386ms, p95 1791ms (in-process, post-warmup)

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.877         0.833         0.600         0.400         1.000         1.000
cross_system        10         0.613         0.550         0.140         0.090         0.600         0.800
prose               11         0.447         0.306         0.164         0.091         0.727         0.818
stat_block           6         0.968         1.000         0.200         0.117         1.000         1.000
table               10         0.651         0.583         0.180         0.130         0.800         0.900
typo_variant        25         0.643         0.560         0.192         0.096         0.880         0.880
all                 65         0.647         0.572         0.197         0.115         0.815         0.877
```

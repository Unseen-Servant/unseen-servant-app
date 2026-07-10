# Retrieval eval baseline — 2026-07-10T15:26:14+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 65 (graded on the specific answer chunk)
Rerank: on
Retrieval: dense
Spell correction: on
Variant expansion: off
search latency over 65 queries: mean 878ms, median 898ms, p95 1217ms (in-process, post-warmup)

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.833         0.778         0.600         0.400         1.000         1.000
cross_system        10         0.554         0.500         0.140         0.080         0.600         0.700
prose               11         0.441         0.298         0.164         0.091         0.727         0.818
stat_block           6         0.968         1.000         0.200         0.117         1.000         1.000
table               10         0.572         0.517         0.160         0.130         0.700         0.800
typo_variant        25         0.593         0.520         0.176         0.088         0.800         0.800
all                 65         0.604         0.535         0.188         0.111         0.769         0.815
```

# Retrieval eval baseline — 2026-07-10T13:37:41+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 60 (graded on the specific answer chunk)
Rerank: on
Retrieval: dense

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.877         0.833         0.600         0.400         1.000         1.000
cross_system        10         0.580         0.550         0.120         0.080         0.600         0.700
prose               11         0.459         0.321         0.164         0.091         0.727         0.818
stat_block           6         0.968         1.000         0.200         0.117         1.000         1.000
table               10         0.648         0.583         0.180         0.140         0.800         0.900
typo_variant        20         0.444         0.342         0.140         0.080         0.600         0.700
all                 60         0.577         0.503         0.177         0.112         0.717         0.800
```

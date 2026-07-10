# Retrieval eval baseline — 2026-07-10T03:06:49+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 40 (graded on the specific answer chunk)
Rerank: on
Retrieval: hybrid

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.877         0.833         0.600         0.400         1.000         1.000
cross_system        10         0.605         0.508         0.180         0.100         0.900         0.900
prose               11         0.396         0.273         0.145         0.082         0.636         0.727
stat_block           6         0.966         1.000         0.200         0.117         1.000         1.000
table               10         0.611         0.533         0.180         0.140         0.800         0.900
all                 40         0.624         0.548         0.205         0.130         0.825         0.875
```

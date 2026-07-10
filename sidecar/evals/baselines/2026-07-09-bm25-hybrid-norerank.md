# Retrieval eval baseline — 2026-07-10T03:07:28+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 40 (graded on the specific answer chunk)
Rerank: off
Retrieval: hybrid

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.865         0.833         0.600         0.400         1.000         1.000
cross_system        10         0.677         0.583         0.180         0.100         0.800         0.900
prose               11         0.431         0.324         0.164         0.082         0.727         0.727
stat_block           6         1.000         1.000         0.200         0.100         1.000         1.000
table               10         0.723         0.658         0.160         0.140         0.800         0.900
all                 40         0.683         0.612         0.205         0.128         0.825         0.875
```

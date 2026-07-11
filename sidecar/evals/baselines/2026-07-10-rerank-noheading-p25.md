# Retrieval eval baseline — 2026-07-11T02:36:13+00:00

Corpus: Basic-Fantasy-RPG-Rules-r142.pdf, Black-Flag-Roleplaying.pdf, SRD_CC_v5.1.pdf
Queries: 65 (graded on the specific answer chunk)
Rerank: on
Retrieval: dense
Spell correction: on
Variant expansion: off
Page size: 25 (metrics graded @10)
search latency over 65 queries: mean 1219ms, median 1246ms, p95 1595ms (in-process, post-warmup)

```
category       queries       ndcg@10         mrr@5   precision@5  precision@10      recall@5     recall@10
----------------------------------------------------------------------------------------------------------
cross_page           3         0.768         0.778         0.400         0.333         1.000         1.000
cross_system        10         0.319         0.253         0.080         0.050         0.400         0.500
prose               11         0.365         0.223         0.109         0.082         0.545         0.727
stat_block           6         0.582         0.500         0.100         0.100         0.500         0.833
table               10         0.593         0.567         0.180         0.130         0.800         0.800
typo_variant        25         0.406         0.304         0.112         0.076         0.560         0.680
all                 65         0.447         0.363         0.129         0.095         0.585         0.708
```

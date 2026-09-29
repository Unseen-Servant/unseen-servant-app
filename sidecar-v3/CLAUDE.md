# sidecar-v3 — pipeline rebuild

Read docs/roadmap/2026-08-13-pipeline-rebuild-plan.md before any work. Non-negotiables:
1. Strictly local. No cloud calls, no PyTorch in packaged code (ONNX only).
2. Spike numbers are priors, not evidence. No brick lands without a Phase 0 harness verdict:
   `uv run python -m evals.run_eval --engine v3` from repo root, baseline committed per rung.
3. Ablation-ladder order (plan §4 Phase 3). Do not implement ahead of the ladder.
4. English-first. Keep `lang` fields; do not build French features now.
5. Consumers: app UI, Claude, and 4B-class local models — compact payloads, MRR@5 first (known-item; recall@3 = answer-in-top-3).
6. Markdown is never the IR. Typed models in domain/models.py carry bbox + page + section.
7. This package must not import from sidecar/ (v2), and vice versa. Shared code is copied, not linked.

---

**Status: paused 2026-09-28.** Phases 0–3 and recovery W1 are built; the shipping pipeline stayed v2.
Before resuming, read the "v3 rebuild paused" row in §8 of
docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md — what v3 taught and what would reopen it.

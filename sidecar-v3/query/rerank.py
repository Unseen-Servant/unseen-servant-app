"""Single-pass cross-encoder rerank (ONNX int8 CPU); the latency gate is
≤500 ms / 25 pairs. Replaces v2's two-pass rerank (plan §3.4, §5).

Intentionally unimplemented — no pipeline code before the Phase 1 verdicts (scaffold §2).
"""

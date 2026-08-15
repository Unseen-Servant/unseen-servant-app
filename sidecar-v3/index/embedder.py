"""bge-m3 dense, int8 ONNX, in-process (no Ollama) — run at full 8192 context
with per-unit token counts logged; batch 64–256, throughput gate ≥25 units/s.
The exact ONNX export is pinned by the embed_parity spike (plan §3.3).

Intentionally unimplemented — no pipeline code before the Phase 1 verdicts (scaffold §2).
"""

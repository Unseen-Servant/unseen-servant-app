"""Per-page min gate for the golden extraction set (recovery strategy W0.2).

The golden suite reports a mean, and a mean let g28 (the SRD 5.1 goblin) drop
1.0 → 0.5 inside a 0.940 aggregate that "beat v2's 0.935" — the run passed,
the chunk got worse. This gate compares every page's every metric against a
reference baseline (the last committed one); any drop fails the run, whatever
the aggregate does. Pages new to the current run and metrics unscored on
either side are not regressions (spec changes are deliberate commits).
"""
from __future__ import annotations

from evals.extraction.grade import METRICS

TOL = 1e-6


def page_regressions(current: list[dict], reference: list[dict],
                     metrics: list[str] = METRICS, tol: float = TOL) -> list[dict]:
    ref_by_id = {p["id"]: p for p in reference}
    out: list[dict] = []
    for cur in current:
        ref = ref_by_id.get(cur["id"])
        if ref is None:
            continue
        for m in metrics:
            r, c = ref.get(m), cur.get(m)
            if r is None or c is None:
                continue
            if c < r - tol:
                out.append({"id": cur["id"], "metric": m, "ref": r, "cur": c})
    return out


def format_regressions(regs: list[dict]) -> str:
    if not regs:
        return "no per-page regressions"
    return "\n".join(f"  {r['id']:5} {r['metric']:15} {r['ref']:.3f} → {r['cur']:.3f}" for r in regs)

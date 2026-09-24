"""Carry a scored blind round onto a later baseline's results by containment.

A blind round labels specific returned chunks. When a later baseline returns
larger texts (Phase 2 sections) that contain those chunks, the label carries:
a section that contains a chunk the human marked relevant is relevant, one
that contains a garbled chunk is garbled. Containment is structural — same
book, the section's heading path is a prefix of the chunk's breadcrumb, and
the section's page span covers the chunk's — so it needs no text.

Reports human MRR@5 as a bound pair: `lo` treats an uncovered chunk (no
labeled chunk inside) as not relevant, `hi` falls back to the auto grade.
When lo ≈ hi the transfer is trustworthy; `covered` says how much of the
top-5 the labels reach.

    uv run --project sidecar python -m evals.blind.transfer \
        evals/baselines/2026-09-12-v2-headings evals/baselines/2026-09-12-v2-sections
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _stem(s: str) -> Path:
    for suf in (".results.json", ".blind.json", ".json", ".md", ".html"):
        if s.endswith(suf):
            return Path(s[: -len(suf)])
    return Path(s)


def contains(sec: dict, ch: dict) -> bool:
    if sec["book"] != ch["book"]:
        return False
    sh, chh = sec["section_heading"] or "", ch["section_heading"] or ""
    if not (chh == sh or chh.startswith(sh + " > ") or sh == ""):
        return False
    return sec["page_start"] <= ch["page_start"] and sec["page_end"] >= ch["page_end"]


def _mrr(rels: list[bool]) -> float:
    for i, r in enumerate(rels[:5]):
        if r:
            return 1 / (i + 1)
    return 0.0


def transfer(labeled: Path, target: Path, top: int = 5) -> dict:
    src = json.loads(Path(f"{labeled}.results.json").read_text())["results"]
    labels = json.loads(Path(f"{labeled}.blind.json").read_text())["labels"]
    dst = json.loads(Path(f"{target}.results.json").read_text())["results"]
    scope = {q["id"]: q["scope"] for q in json.loads(Path(f"{target}.json").read_text())["per_query"]}
    rows: dict[str, dict] = {}
    for qid, secs in dst.items():
        lab = labels.get(qid, {})
        rel, gar = set(lab.get("relevant", [])), set(lab.get("garbled", []))
        chunks = [c for c in src[qid] if c["rank"] <= top]
        d = rows.setdefault(scope[qid], {"n": 0, "lo": 0.0, "hi": 0.0, "auto": 0.0,
                                         "covered": 0, "total": 0, "garbled": 0})
        lo, hi, auto = [], [], []
        for sec in sorted(secs, key=lambda c: c["rank"])[:top]:
            inside = [c for c in chunks if contains(sec, c)]
            d["total"] += 1
            auto.append(bool(sec.get("matched")))
            if inside:
                d["covered"] += 1
                hrel = any(c["rank"] in rel for c in inside)
                lo.append(hrel); hi.append(hrel)
                d["garbled"] += any(c["rank"] in gar for c in inside)
            else:
                lo.append(False); hi.append(bool(sec.get("matched")))
        d["n"] += 1; d["lo"] += _mrr(lo); d["hi"] += _mrr(hi); d["auto"] += _mrr(auto)
    allrow = {"n": 0, "lo": 0.0, "hi": 0.0, "auto": 0.0, "covered": 0, "total": 0, "garbled": 0}
    for d in rows.values():
        for k in allrow:
            allrow[k] += d[k]
    rows["all"] = allrow
    return rows


def format_report(rows: dict) -> str:
    out = [f"{'scope':<8}{'q':>4}{'auto mrr':>10}{'human lo':>10}{'human hi':>10}{'readable@5':>12}{'covered':>9}"]
    for sc, d in rows.items():
        n = d["n"]
        out.append(f"{sc:<8}{n:>4}{d['auto']/n:>10.3f}{d['lo']/n:>10.3f}{d['hi']/n:>10.3f}"
                   f"{1 - d['garbled']/d['total']:>12.3f}{d['covered']/d['total']:>9.0%}")
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__); return 2
    print(format_report(transfer(_stem(sys.argv[1]), _stem(sys.argv[2]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

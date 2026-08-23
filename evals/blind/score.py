"""Scoring key — does the deterministic anchor grade agree with a human?

Reads a baseline's auto grade (``<stem>.results.json`` — each chunk's
``matched`` is the scope-aware anchor judgment) and a human's blind labels
(``<stem>.blind.json`` from blind/generate.py) over the top-N chunks, and
reports:

- a TRUST number — per-chunk human-vs-auto agreement + Cohen's kappa,
- METRIC agreement per scope — auto MRR@5 / recall vs the same recomputed
  from the human labels (does the automated number track the human one?),
- DISAGREEMENTS to act on — false-MISS (human relevant, anchor said no →
  anchor too strict) and false-hit (anchor said yes, human said no),
- READABILITY — readable@5 = 1 − garbled/top per query (the "garbled" tick;
  recovery strategy W0.4). Exports from before the tick score "—", not 1.0.

    uv run --project sidecar python -m evals.blind.score \
        evals/baselines/2026-08-15-v2-phase0

Only queries the human marked `reviewed` are scored. Writes <stem>.blind.md.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evals.retrieval.metrics import mrr_at, recall_at

COMPARE = ["mrr@5", "recall@3", "recall@5"]  # all computable within top-5


def _stem(path) -> Path:
    s = str(path)
    for suffix in (".results.json", ".blind.json", ".blind.md", ".json", ".html", ".md"):
        if s.endswith(suffix):
            return Path(s[: -len(suffix)])
    return Path(s)


def _metrics(rels: list[bool]) -> dict:
    return {"mrr@5": mrr_at(rels, 5), "recall@3": recall_at(rels, 3), "recall@5": recall_at(rels, 5)}


def _kappa(pairs: list[tuple[bool, bool]]) -> float:
    n = len(pairs)
    if not n:
        return 0.0
    po = sum(a == b for a, b in pairs) / n
    pa1, ph1 = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa1 * ph1 + (1 - pa1) * (1 - ph1)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def score(stem) -> dict:
    stem = _stem(stem)
    baseline = json.loads(Path(f"{stem}.json").read_text(encoding="utf-8"))
    results = json.loads(Path(f"{stem}.results.json").read_text(encoding="utf-8"))["results"]
    blind = json.loads(Path(f"{stem}.blind.json").read_text(encoding="utf-8"))
    labels, top = blind["labels"], blind.get("top", 5)
    scope_of = {q["id"]: q.get("scope", "cued") for q in baseline["per_query"]}
    query_of = {q["id"]: q["query"] for q in baseline["per_query"]}

    pairs_by_scope: dict[str, list] = defaultdict(list)
    auto_by_scope: dict[str, list] = defaultdict(list)
    human_by_scope: dict[str, list] = defaultdict(list)
    readable_by_scope: dict[str, list] = defaultdict(list)   # (n_chunks, n_garbled) per query
    disagreements, garbled_chunks = [], []
    reviewed = skipped = 0

    for qid, chunks in results.items():
        lab = labels.get(qid)
        if not lab or not lab.get("reviewed"):
            skipped += 1
            continue
        reviewed += 1
        scope = scope_of.get(qid, "cued")
        human_rel = set(lab.get("relevant", []))
        garbled = set(lab["garbled"]) if "garbled" in lab else None   # None: sheet predates the tick
        top_chunks = sorted(chunks, key=lambda c: c["rank"])[:top]
        if garbled is not None:
            hit = [c for c in top_chunks if c["rank"] in garbled]
            readable_by_scope[scope].append((len(top_chunks), len(hit)))
            garbled_chunks += [{"query": query_of.get(qid, qid), "qid": qid, "scope": scope,
                                "rank": c["rank"], "book": c["book"], "snippet": c["snippet"][:160]}
                               for c in hit]
        auto_rels, human_rels = [], []
        for c in top_chunks:
            auto, human = bool(c["matched"]), c["rank"] in human_rel
            auto_rels.append(auto)
            human_rels.append(human)
            pairs_by_scope[scope].append((auto, human))
            if auto != human:
                disagreements.append({
                    "query": query_of.get(qid, qid), "qid": qid, "scope": scope,
                    "rank": c["rank"], "book": c["book"],
                    "kind": "false-MISS (anchor too strict)" if human else "false-hit (anchor too loose)",
                    "snippet": c["snippet"][:160],
                })
        auto_by_scope[scope].append(_metrics(auto_rels))
        human_by_scope[scope].append(_metrics(human_rels))

    scopes = sorted(pairs_by_scope) + ["all"]
    agreement = {}
    for s in scopes:
        pairs = [p for sc in pairs_by_scope for p in pairs_by_scope[sc]] if s == "all" else pairs_by_scope[s]
        agreement[s] = {
            "chunks": len(pairs),
            "agree": sum(a == b for a, b in pairs) / len(pairs) if pairs else None,
            "kappa": _kappa(pairs),
        }
    metric_cmp = {}
    for s in scopes:
        auto = [m for sc in auto_by_scope for m in auto_by_scope[sc]] if s == "all" else auto_by_scope[s]
        human = [m for sc in human_by_scope for m in human_by_scope[sc]] if s == "all" else human_by_scope[s]
        metric_cmp[s] = {
            "queries": len(auto),
            **{m: {"auto": sum(a[m] for a in auto) / len(auto) if auto else None,
                   "human": sum(h[m] for h in human) / len(human) if human else None}
               for m in COMPARE},
        }
    readability = {}
    for s in scopes:
        rows = ([r for sc in readable_by_scope for r in readable_by_scope[sc]] if s == "all"
                else readable_by_scope[s])
        readability[s] = {
            "queries": len(rows),
            "garbled": sum(g for _, g in rows),
            "readable@5": sum(1 - g / n for n, g in rows if n) / len(rows) if rows else None,
        }
    return {"reviewed": reviewed, "skipped": skipped, "top": top,
            "agreement": agreement, "metric_cmp": metric_cmp, "disagreements": disagreements,
            "readability": readability, "garbled_chunks": garbled_chunks}


def render_md(stem, r: dict) -> str:
    lines = [f"# Blind scoring — {_stem(stem).name}", "",
             f"Reviewed {r['reviewed']} queries (skipped {r['skipped']} un-reviewed); top-{r['top']} chunks each.",
             "", "## Trust: human vs auto (anchor) per chunk", "```",
             f"{'scope':<10}{'chunks':>8}{'agree':>9}{'kappa':>9}"]
    for s, a in r["agreement"].items():
        ag = f"{a['agree']:.3f}" if a["agree"] is not None else "—"
        lines.append(f"{s:<10}{a['chunks']:>8}{ag:>9}{a['kappa']:>9.3f}")
    lines += ["```", "", "## Metric agreement (does the automated number track the human's?)", "```",
              f"{'scope':<10}{'q':>4}" + "".join(f"{k + ' (a/h)':>18}" for k in COMPARE)]

    def _cell(v: dict) -> str:
        s = f"{v['auto']:.2f}/{v['human']:.2f}" if v["auto"] is not None else "—"
        return f"{s:>18}"

    for s, m in r["metric_cmp"].items():
        lines.append(f"{s:<10}{m['queries']:>4}" + "".join(_cell(m[k]) for k in COMPARE))
    lines += ["```", "", "## Readability (human: the garbled tick)", "```",
              f"{'scope':<10}{'q':>4}{'garbled':>9}{'readable@5':>12}"]
    for s, v in r["readability"].items():
        rd = f"{v['readable@5']:.3f}" if v["readable@5"] is not None else "—"
        lines.append(f"{s:<10}{v['queries']:>4}{v['garbled']:>9}{rd:>12}")
    lines += ["```", "", f"## Garbled chunks ({len(r['garbled_chunks'])})"]
    for g in r["garbled_chunks"]:
        lines.append(f"- [{g['scope']}] {g['qid']} \"{g['query']}\" — #{g['rank']} {g['book']}  · {g['snippet']!r}")
    lines += ["", f"## Disagreements to act on ({len(r['disagreements'])})"]
    for d in r["disagreements"]:
        lines.append(f"- [{d['scope']}] {d['qid']} \"{d['query']}\" — #{d['rank']} {d['book']}: "
                     f"**{d['kind']}**  · {d['snippet']!r}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("baseline", help="baseline stem (needs <stem>.results.json and <stem>.blind.json)")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    bjson = Path(f"{_stem(args.baseline)}.blind.json")
    if not bjson.exists():
        raise SystemExit(f"no human labels at {bjson} — score the blind scoresheet and Export first.")
    r = score(args.baseline)
    md = render_md(args.baseline, r)
    print(md)
    if not args.no_write:
        out = Path(f"{_stem(args.baseline)}.blind.md")
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

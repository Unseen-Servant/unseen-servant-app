"""Phase 0 eval runner — grade an engine against the pinned query set.

    uv run --project sidecar python -m evals.run_eval --engine v2 \
        --baseline phase0

Verifies the corpus (refuses on any hash/digest drift), indexes the PDFs
the queries reference, runs each query through the engine at the UI's page
size, grades anchor-in-chunk relevance, and writes a committed baseline
(JSON + MD) under evals/baselines/. Knobs are pinned in SearchOptions so a
baseline measures exactly what it claims (the run_eval.py rule).
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

import yaml

from evals.corpus import require_corpus
from evals.engines.base import SearchOptions
from evals.retrieval import grade, metrics

QUERIES_PATH = Path(__file__).resolve().parent / "retrieval" / "queries.yaml"
BASELINE_DIR = Path(__file__).resolve().parent / "baselines"


def build_engine(name: str, data_dir: Path | None):
    if name == "v2":
        from evals.engines.v2 import V2Engine, DEFAULT_DATA_DIR

        return V2Engine(data_dir=data_dir or DEFAULT_DATA_DIR)
    if name == "v3":
        raise SystemExit("v3 engine is a stub until Phase 2 (scaffold §2).")
    raise SystemExit(f"unknown engine {name!r}")


def run(engine, queries: list[dict], corpus, opts: SearchOptions, do_index: bool) -> dict:
    doc_file = {d.id: d.pdf_path.name for d in corpus.documents}
    doc_pdf = {d.id: d.pdf_path for d in corpus.documents}

    if do_index:
        needed = sorted({q["doc"] for q in queries if q["doc"] != "any"})
        print(f"indexing {len(needed)} corpus PDFs (idempotent, one at a time)…", flush=True)
        for i, d in enumerate(needed, 1):
            rep = engine.index([doc_pdf[d]])
            state = "skipped (already indexed)" if rep.skipped else f"indexed ({rep.indexed})"
            print(f"  [{i}/{len(needed)}] {d}: {state}"
                  + (f" errors={rep.errors}" if rep.errors else ""), flush=True)

    print("warmup…", flush=True)
    engine.warmup(opts)

    per_query, latencies = [], []
    results_by_query: dict[str, list[dict]] = {}
    for q in queries:
        resp = engine.search(q["query"], opts)
        doc_fn = None if q["doc"] == "any" else doc_file.get(q["doc"])
        g = grade.grade_response(resp, q, doc_fn)
        # Trimmed retrieved chunks for the HTML inspector (gitignored side file).
        results_by_query[q["id"]] = [
            {
                "rank": i,
                "book": r.filename,
                "section_heading": r.section_heading,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "relevance": round(r.relevance, 4),
                "tier": r.tier,
                "reranked": r.reranked,
                "matched": bool(matched),
                "snippet": (r.text or "").strip()[:200],
            }
            for i, (r, matched) in enumerate(zip(resp.results, g["rels"]), 1)
        ]
        per_query.append({
            "id": q["id"], "pair": q["pair"], "style": q["style"],
            "category": q["category"], "doc": q["doc"], "query": q["query"],
            "metrics": {
                **metrics.rank_metrics(g["rels"]),
                "payload_chars": g["payload_chars"],
                "dup_sections@10": g["dup_sections@10"],
            },
            "latency_ms": resp.latency_ms,
            "page_hit": g["page_hit"],
            "hit_rank": next((i + 1 for i, r in enumerate(g["rels"]) if r), None),
            "corrected_query": resp.corrected_query,
        })
        latencies.append(resp.latency_ms)
        mark = f"#{per_query[-1]['hit_rank']}" if per_query[-1]["hit_rank"] else "MISS"
        print(f"  {q['id']} [{q['style']:<7}] {mark:>5}  {q['query'][:52]}", flush=True)

    return {
        "by_category": metrics.aggregate(per_query, "category"),
        "by_style": metrics.aggregate(per_query, "style"),
        "latency": metrics.latency_stats(latencies),
        "per_query": per_query,
        "results": results_by_query,
    }


def render_md(meta: dict, result: dict) -> str:
    lat = result["latency"]
    return "\n".join([
        f"# Retrieval baseline — {meta['engine']} — {meta['name']}",
        "",
        f"Date: {meta['date']}",
        f"Corpus docs: {', '.join(meta['docs'])}",
        f"Queries: {meta['n_queries']} ({meta['n_pairs']} pairs)  |  n_results: {meta['n_results']}",
        f"Knobs: rerank={meta['opts']['rerank']} hybrid={meta['opts']['hybrid']} "
        f"spell_correction={meta['opts']['spell_correction']} "
        f"variant_expansion={meta['opts']['variant_expansion']}",
        "",
        "## By category",
        "```", metrics.format_report(result["by_category"], "category"), "```",
        "",
        "## By style",
        "```", metrics.format_report(result["by_style"], "style"), "```",
        "",
        f"Search latency over {lat['count']} queries: "
        f"mean {lat['mean_ms']:.0f}ms, p50 {lat['p50_ms']:.0f}ms, p95 {lat['p95_ms']:.0f}ms",
        "",
        f"Misses: {', '.join(q['id'] for q in result['per_query'] if q['hit_rank'] is None) or 'none'}",
        "",
    ])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", default="v2", choices=["v2", "v3"])
    ap.add_argument("--suite", default="retrieval", choices=["retrieval"])
    ap.add_argument("--baseline", default="phase0", help="baseline name (rung)")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--n-results", type=int, default=SearchOptions.n_results)
    ap.add_argument("--no-index", action="store_true", help="assume corpus already indexed")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N queries")
    ap.add_argument("--no-write", action="store_true", help="print but do not write a baseline")
    args = ap.parse_args()

    corpus = require_corpus()  # refuses on any hash/digest drift (§1)
    queries = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))
    if args.limit:
        queries = queries[: args.limit]

    opts = SearchOptions(n_results=args.n_results)
    engine = build_engine(args.engine, args.data_dir)
    try:
        result = run(engine, queries, corpus, opts, do_index=not args.no_index)
    finally:
        engine.close()

    print("\n## By category\n" + metrics.format_report(result["by_category"], "category"))
    print("\n## By style\n" + metrics.format_report(result["by_style"], "style"))
    lat = result["latency"]
    print(f"\nlatency: mean {lat['mean_ms']:.0f}ms  p50 {lat['p50_ms']:.0f}ms  p95 {lat['p95_ms']:.0f}ms")

    meta = {
        "engine": args.engine, "name": args.baseline,
        "date": datetime.date.today().isoformat(),
        "docs": sorted({q["doc"] for q in queries if q["doc"] != "any"}),
        "n_queries": len(queries), "n_pairs": len({q["pair"] for q in queries}),
        "n_results": args.n_results,
        "opts": {"rerank": opts.rerank, "hybrid": opts.hybrid,
                 "spell_correction": opts.spell_correction,
                 "variant_expansion": opts.variant_expansion},
    }

    if not args.no_write:
        from evals.retrieval import report

        BASELINE_DIR.mkdir(exist_ok=True)
        stem = f"{meta['date']}-{args.engine}-{args.baseline}"
        # Retrieved chunks are pulled out of the committed baseline so its
        # diff stays a clean metrics review (§6); they live in a gitignored
        # side file that drives the HTML inspector.
        results = result.pop("results", {})
        (BASELINE_DIR / f"{stem}.json").write_text(
            json.dumps({"meta": meta, **result}, indent=2), encoding="utf-8")
        (BASELINE_DIR / f"{stem}.md").write_text(render_md(meta, result), encoding="utf-8")
        (BASELINE_DIR / f"{stem}.results.json").write_text(
            json.dumps({"meta": {k: meta[k] for k in ("engine", "name", "date", "n_results")},
                        "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
        report.write_html(BASELINE_DIR / stem)
        print(f"\nwrote evals/baselines/{stem}.{{json,md,results.json,html}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

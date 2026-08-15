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
from dataclasses import replace
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
        # Scope decides how we search and how we grade (v3 scaffold §3):
        #   single — filter search to the intended file; grade anchors only
        #            (the filter guarantees the system).
        #   cued   — unfiltered; the query names the system; grade anchors AND
        #            right file (the right system must win over other systems).
        #   uncued — unfiltered; the query omits the system; grade anchors, any
        #            file (a correct answer from any system counts). `doc` is
        #            kept as the representative for anchor verification only.
        scope = q.get("scope", "cued")
        doc_fn = None if q["doc"] == "any" else doc_file.get(q["doc"])
        if scope == "single":
            q_opts, grade_doc = replace(opts, source_filter=doc_fn), None
        elif scope == "uncued":
            q_opts, grade_doc = opts, None
        else:  # cued
            q_opts, grade_doc = opts, doc_fn
        resp = engine.search(q["query"], q_opts)
        g = grade.grade_response(resp, q, grade_doc)
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
            "category": q["category"], "scope": scope, "doc": q["doc"],
            "query": q["query"],
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
        print(f"  {q['id']} [{scope:<6} {q['style']:<7}] {mark:>5}  {q['query'][:48]}", flush=True)

    return {
        "by_category": metrics.aggregate(per_query, "category"),
        "by_style": metrics.aggregate(per_query, "style"),
        "by_scope": metrics.aggregate(per_query, "scope"),
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
        "## By scope",
        "```", metrics.format_report(result["by_scope"], "scope"), "```",
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


# ── extraction suite ──────────────────────────────────────────────────────

def run_extraction(engine, corpus) -> dict:
    """Extract each golden doc once (engine.extract, no Ollama needed) and
    grade its golden pages against the hand-authored specs."""
    from evals.extraction import grade as xgrade
    from evals.extraction.verify_golden import load_golden

    specs = load_golden()
    if not specs:
        raise SystemExit("no golden specs in evals/extraction/golden/ — author some first.")
    doc_pdf = {d.id: d.pdf_path for d in corpus.documents}
    pages_by_doc: dict[str, dict[int, str]] = {}
    for d in sorted({s["doc"] for s in specs}):
        print(f"extracting {d}…", flush=True)
        pages_by_doc[d] = {p.page_number: p.text for p in engine.extract(doc_pdf[d])}

    graded = []
    for s in specs:
        # Grade against a ±1-page window anchored on the golden page: pymupdf4llm
        # (and v3's future extractor) attribute page-boundary content slightly
        # differently than the fitz text we verify golden specs against, so an
        # exact-page match would score segmenter drift, not extraction quality.
        pages = pages_by_doc.get(s["doc"], {})
        p = s["page"]
        window = "\n\n".join(pages.get(pp, "") for pp in (p - 1, p, p + 1))
        g = xgrade.grade_page(s, window)
        graded.append(g)
        scored = " ".join(f"{m}={g[m]:.2f}" for m in xgrade.METRICS if g.get(m) is not None)
        print(f"  {s['id']} [{s['kind']:10}] {s['doc']} p.{s['page']}  {scored}", flush=True)
    return {
        "by_kind": xgrade.aggregate(graded, "kind"),
        "by_doc": xgrade.aggregate(graded, "doc"),
        "pages": graded,
    }


def extraction_report(summary: dict, title: str) -> str:
    from evals.extraction.grade import METRICS as XM

    header = f"{title:<16}{'pages':>7}" + "".join(f"{m:>16}" for m in XM)
    lines = [header, "-" * len(header)]
    for c in sorted(c for c in summary if c != "all") + ["all"]:
        r = summary[c]
        cells = "".join(
            f"{(format(r[m], '.3f') if r.get(m) is not None else '—'):>16}" for m in XM)
        lines.append(f"{c:<16}{r['pages']:>7}" + cells)
    return "\n".join(lines)


def extraction_md(meta: dict, result: dict) -> str:
    return "\n".join([
        f"# Extraction baseline — {meta['engine']} — {meta['name']}",
        "", f"Date: {meta['date']}",
        f"Golden pages: {meta['n_pages']} across {', '.join(meta['docs'])}",
        "", "## By kind", "```", extraction_report(result["by_kind"], "kind"), "```",
        "", "## By doc", "```", extraction_report(result["by_doc"], "doc"), "```", "",
    ])


# ── entry point ───────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", default="v2", choices=["v2", "v3"])
    ap.add_argument("--suite", default="retrieval", choices=["retrieval", "extraction"])
    ap.add_argument("--baseline", default=None, help="baseline name (rung); default: the suite name")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--n-results", type=int, default=SearchOptions.n_results)
    ap.add_argument("--no-index", action="store_true", help="retrieval: assume corpus already indexed")
    ap.add_argument("--limit", type=int, default=None, help="retrieval: run only the first N queries")
    ap.add_argument("--no-write", action="store_true", help="print but do not write a baseline")
    args = ap.parse_args()

    corpus = require_corpus()  # refuses on any hash/digest drift (§1)
    name = args.baseline or ("phase0" if args.suite == "retrieval" else "extraction")
    date = datetime.date.today().isoformat()
    stem = f"{date}-{args.engine}-{name}"
    engine = build_engine(args.engine, args.data_dir)

    try:
        if args.suite == "extraction":
            result = run_extraction(engine, corpus)
        else:
            queries = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))
            if args.limit:
                queries = queries[: args.limit]
            opts = SearchOptions(n_results=args.n_results)
            result = run(engine, queries, corpus, opts, do_index=not args.no_index)
    finally:
        engine.close()

    if args.suite == "extraction":
        print("\n## By kind\n" + extraction_report(result["by_kind"], "kind"))
        print("\n## By doc\n" + extraction_report(result["by_doc"], "doc"))
        meta = {"engine": args.engine, "name": name, "date": date,
                "docs": sorted({p["doc"] for p in result["pages"]}),
                "n_pages": len(result["pages"])}
        if not args.no_write:
            BASELINE_DIR.mkdir(exist_ok=True)
            (BASELINE_DIR / f"{stem}.json").write_text(
                json.dumps({"meta": meta, **result}, indent=2), encoding="utf-8")
            (BASELINE_DIR / f"{stem}.md").write_text(extraction_md(meta, result), encoding="utf-8")
            print(f"\nwrote evals/baselines/{stem}.{{json,md}}")
        return 0

    print("\n## By scope\n" + metrics.format_report(result["by_scope"], "scope"))
    print("\n## By category\n" + metrics.format_report(result["by_category"], "category"))
    print("\n## By style\n" + metrics.format_report(result["by_style"], "style"))
    lat = result["latency"]
    print(f"\nlatency: mean {lat['mean_ms']:.0f}ms  p50 {lat['p50_ms']:.0f}ms  p95 {lat['p95_ms']:.0f}ms")

    meta = {
        "engine": args.engine, "name": name, "date": date,
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

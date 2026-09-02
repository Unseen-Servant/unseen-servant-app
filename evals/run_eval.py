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
import hashlib
import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import yaml

from evals.corpus import require_corpus
from evals.engines.base import SearchOptions
from evals.retrieval import grade, metrics

QUERIES_PATH = Path(__file__).resolve().parent / "retrieval" / "queries.yaml"
BASELINE_DIR = Path(__file__).resolve().parent / "baselines"

# Rung-6 system-boost keyword map — the eval's stand-in for the product's tag
# keyword lists (user-defined + defaults). Keyword → the doc ids it names; built
# into {keyword: {filenames}} against the corpus. Production wires this to tags.
SYSTEM_KEYWORDS = {
    "bfrpg_4e": ["basic fantasy", "bfrpg"],
    "black_hack_1e": ["black hack"],
    "cairn_1e": ["cairn"],
    "srd_5_1": ["dnd", "d&d", "5e"],
    "srd_5_2_1": ["dnd", "d&d", "5e"],
    "osric_2e": ["osric"],
    "yze_srd": ["year zero", "yze"],
}


def _system_map(corpus) -> dict:
    m: dict[str, set] = {}
    for d in corpus.documents:
        for kw in SYSTEM_KEYWORDS.get(d.id, []):
            m.setdefault(kw, set()).add(d.pdf_path.name)
    return m


# The same information as SYSTEM_KEYWORDS, in the shape the v2 product stores
# it: a tag per book (custom systems for the five books game_systems.py does
# not know; the built-in "D&D 5E" for both SRDs) plus the keywords that make
# detect_systems_in_query recognise the tag in a query. Without this the v2
# eval index is untagged and _system_boost_factors is a no-op on 5 of 7 books
# (roadmap §1.5). Production wires the same thing to the user's tag lists.
SYSTEM_TAGS: dict[str, tuple[str, list[str]]] = {
    "bfrpg_4e": ("Basic Fantasy RPG", SYSTEM_KEYWORDS["bfrpg_4e"]),
    "black_hack_1e": ("The Black Hack", SYSTEM_KEYWORDS["black_hack_1e"]),
    "cairn_1e": ("Cairn", SYSTEM_KEYWORDS["cairn_1e"]),
    "srd_5_1": ("D&D 5E", SYSTEM_KEYWORDS["srd_5_1"]),
    "srd_5_2_1": ("D&D 5E", SYSTEM_KEYWORDS["srd_5_2_1"]),
    "osric_2e": ("OSRIC", SYSTEM_KEYWORDS["osric_2e"]),
    "yze_srd": ("Year Zero Engine", SYSTEM_KEYWORDS["yze_srd"]),
}


def query_docs(q: dict) -> list[str]:
    """A query's doc ids. ``doc`` is a str, a list (edition twins for one
    cue — any listed file is the right file), or ``"any"`` (→ [])."""
    doc = q["doc"]
    if doc == "any":
        return []
    return list(doc) if isinstance(doc, list) else [doc]


def build_engine(name: str, data_dir: Path | None, pdf_backend: str = "pymupdf"):
    if name == "v2":
        from evals.engines.v2 import V2Engine, DEFAULT_DATA_DIR

        return V2Engine(data_dir=data_dir or DEFAULT_DATA_DIR)
    if name == "v3":
        from evals.engines.v3 import V3Engine, DEFAULT_DATA_DIR

        return V3Engine(data_dir=data_dir or DEFAULT_DATA_DIR, pdf_backend=pdf_backend)
    raise SystemExit(f"unknown engine {name!r}")


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return sorted(_jsonable(v) for v in value)
    return value


def corpus_fingerprint(corpus) -> str:
    """Stable identity for the exact PDF/reference inputs in an eval run."""
    documents = [
        {"id": d.id, "pdf_sha256": d.pdf_sha256, "ref_digest": d.ref_digest}
        for d in sorted(corpus.documents, key=lambda d: d.id)
    ]
    payload = json.dumps(documents, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def retrieval_regressions(current: dict, reference: dict, tol: float = 1e-6) -> list[dict]:
    """Fail closed on a headline retrieval regression in any shared scope."""
    out: list[dict] = []
    current_scopes = current.get("by_scope", {})
    reference_scopes = reference.get("by_scope", {})
    for scope in sorted(set(current_scopes) & set(reference_scopes)):
        for metric in ("mrr@5", "recall@3"):
            cur = current_scopes[scope].get(metric)
            ref = reference_scopes[scope].get(metric)
            if cur is None or ref is None:
                continue
            if cur < ref - tol:
                out.append({"scope": scope, "metric": metric, "ref": ref, "cur": cur})
    return out


def format_retrieval_regressions(regressions: list[dict]) -> str:
    if not regressions:
        return "no retrieval regressions"
    return "\n".join(
        f"  {r['scope']:8} {r['metric']:10} {r['ref']:.3f} → {r['cur']:.3f}"
        for r in regressions
    )


def run(engine, queries: list[dict], corpus, opts: SearchOptions, do_index: bool,
        tags: dict[str, tuple[str, list[str]]] | None = None) -> dict:
    doc_file = {d.id: d.pdf_path.name for d in corpus.documents}
    doc_pdf = {d.id: d.pdf_path for d in corpus.documents}
    needed = sorted({d for q in queries for d in query_docs(q)})

    if do_index:
        print(f"indexing {len(needed)} corpus PDFs (idempotent, one at a time)…", flush=True)
        index_errors: list[tuple[str, list]] = []
        for i, d in enumerate(needed, 1):
            rep = engine.index([doc_pdf[d]])
            state = "skipped (already indexed)" if rep.skipped else f"indexed ({rep.indexed})"
            print(f"  [{i}/{len(needed)}] {d}: {state}"
                  + (f" errors={rep.errors}" if rep.errors else ""), flush=True)
            if rep.errors:
                index_errors.append((d, rep.errors))
        if index_errors:
            details = "; ".join(f"{doc}: {errors}" for doc, errors in index_errors)
            raise SystemExit(f"indexing failed; retrieval results are invalid: {details}")

    # Tag after indexing (set-game-systems rewrites the chunk metadata of an
    # indexed file) and before warmup, so the boost sees the tags on every run.
    tag_fn = getattr(engine, "tag_systems", None)
    if tags and tag_fn is not None:
        for d in needed:
            if d in tags:
                tag, keywords = tags[d]
                tag_fn(doc_file[d], tag, keywords)
                print(f"  tagged {d} as {tag!r}", flush=True)

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
        docs = query_docs(q)
        if scope == "single":
            if len(docs) != 1:
                raise SystemExit(f"{q['id']}: single-scope queries need exactly one doc (got {docs})")
            q_opts, grade_doc = replace(opts, source_filter=doc_file[docs[0]]), None
        elif scope == "uncued":
            q_opts, grade_doc = opts, None
        else:  # cued: the right file must win; a list means any listed file is right
            q_opts, grade_doc = opts, {doc_file[d] for d in docs} or None
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
                "snippet": (r.text or "").strip()[:2500],
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


# ── corpus-wide extraction QA (recovery strategy W0.1) ────────────────────

def run_corpus_qa(engine, corpus, saved_texts: dict | None = None) -> dict:
    """Extract EVERY corpus page (engine.extract, no embedding) and grade each
    against the PDF's own PyMuPDF text blocks — the interleave / torn-label
    detector the 30-page golden mean cannot be. ``saved_texts`` (a prior run's
    .pages.json) re-grades without re-extracting — the metric-work inner loop."""
    import pymupdf

    from evals.extraction import corpus_qa

    pages: list[dict] = []
    texts: dict[str, dict[int, str]] = {}   # engine page text, kept for drill-in (side file)
    for d in corpus.documents:
        if saved_texts is not None:
            extracted = {int(k): v for k, v in saved_texts.get(d.id, {}).items()}
        else:
            print(f"extracting {d.id}…", flush=True)
            extracted = {p.page_number: p.text for p in engine.extract(d.pdf_path)}
        texts[d.id] = extracted
        pdf = pymupdf.open(str(d.pdf_path))
        for i, page in enumerate(pdf):
            blocks = corpus_qa.native_blocks(page)
            if not blocks:
                continue
            g = corpus_qa.grade_page(extracted.get(i + 1, ""), blocks)
            pages.append({"doc": d.id, "page": i + 1, **g})
        by_doc = corpus_qa.aggregate([p for p in pages if p["doc"] == d.id])[d.id]
        print(f"  {d.id}: {by_doc['pages']} pages, {by_doc['broken']} broken blocks on "
              f"{by_doc['pages_with_broken']} pages, label_integrity="
              f"{by_doc['label_integrity'] if by_doc['label_integrity'] is None else round(by_doc['label_integrity'], 3)}",
              flush=True)
    return {"by_doc": corpus_qa.aggregate(pages), "worst": corpus_qa.worst_pages(pages),
            "empty": corpus_qa.empty_pages(pages), "pages": pages, "texts": texts}


# ── entry point ───────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", default="v2", choices=["v2", "v3"])
    ap.add_argument("--pdf-backend", default="pymupdf", choices=["pymupdf", "pdfium", "pdfplumber"],
                    help="v3 extraction backend; non-default backends are evaluation candidates")
    ap.add_argument("--suite", default="retrieval", choices=["retrieval", "extraction", "corpus-qa"])
    ap.add_argument("--baseline", default=None, help="baseline name (rung); default: the suite name")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="retrieval: existing index directory, only with --reuse-index")
    ap.add_argument("--n-results", type=int, default=SearchOptions.n_results)
    ap.add_argument("--no-index", action="store_true", help="retrieval: assume corpus already indexed")
    ap.add_argument("--reuse-index", action="store_true",
                    help="retrieval: use --data-dir for an exploratory, non-baseline run")
    ap.add_argument("--hybrid", action="store_true", help="retrieval: fuse dense + BM25/FTS (rung 5)")
    ap.add_argument("--lex-weight", type=float, default=None,
                    help="retrieval: RRF lexical weight (dense=1.0); sweep the fusion balance")
    ap.add_argument("--rerank-weight", type=float, default=None,
                    help="retrieval: RRF rerank blend weight (retrieval=1.0); sweep the rerank pull")
    ap.add_argument("--limit", type=int, default=None, help="retrieval: run only the first N queries")
    ap.add_argument("--no-write", action="store_true", help="print but do not write a baseline")
    ap.add_argument("--pages", type=Path, default=None,
                    help="corpus-qa: re-grade a prior run's .pages.json instead of re-extracting")
    ap.add_argument("--gate", type=Path, default=None,
                    help="reference baseline .json; retrieval blocks headline scope regressions, "
                         "extraction blocks any per-page metric regression")
    args = ap.parse_args()

    if args.suite == "retrieval":
        if args.reuse_index and args.data_dir is None:
            raise SystemExit("--reuse-index requires --data-dir")
        if args.data_dir is not None and not args.reuse_index:
            raise SystemExit("retrieval --data-dir requires --reuse-index; normal runs use a fresh index")
        if args.no_index and not args.reuse_index:
            raise SystemExit("--no-index requires --reuse-index and --data-dir")
        if args.reuse_index and not args.no_write:
            raise SystemExit("reused-index retrieval runs cannot write a baseline; use a fresh index")

    corpus = require_corpus()  # refuses on any hash/digest drift (§1)
    name = args.baseline or {"retrieval": "phase0", "extraction": "extraction",
                             "corpus-qa": "corpus-qa"}[args.suite]
    date = datetime.date.today().isoformat()
    stem = f"{date}-{args.engine}-{name}"
    temporary_index = None
    data_dir = args.data_dir
    if args.suite == "retrieval" and not args.reuse_index:
        temporary_index = tempfile.TemporaryDirectory(prefix=f"legend-lore-eval-{args.engine}-")
        data_dir = Path(temporary_index.name)
    if args.engine == "v2" and args.pdf_backend != "pymupdf":
        raise SystemExit("non-default --pdf-backend values are available only with --engine v3")
    engine = build_engine(args.engine, data_dir, args.pdf_backend)

    try:
        if args.suite == "extraction":
            result = run_extraction(engine, corpus)
        elif args.suite == "corpus-qa":
            saved = json.loads(args.pages.read_text(encoding="utf-8")) if args.pages else None
            result = run_corpus_qa(engine, corpus, saved_texts=saved)
        else:
            queries = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))
            if args.limit:
                queries = queries[: args.limit]
            extra: dict = {"system_map": _system_map(corpus)}  # rung 6 boost (no-op if no system named)
            if args.lex_weight is not None:
                extra["weights"] = [1.0, args.lex_weight]
            if args.rerank_weight is not None:
                extra["rerank_weight"] = args.rerank_weight
            opts = SearchOptions(n_results=args.n_results, hybrid=args.hybrid, extra=extra)
            result = run(engine, queries, corpus, opts, do_index=not args.no_index,
                         tags=SYSTEM_TAGS if args.engine == "v2" else None)
    finally:
        engine.close()
        if temporary_index is not None:
            temporary_index.cleanup()

    if args.suite == "corpus-qa":
        from evals.extraction import corpus_qa

        meta = {"engine": args.engine, "name": name, "date": date}
        md = corpus_qa.render_md(meta, result)
        print("\n" + md)
        if not args.no_write:
            BASELINE_DIR.mkdir(exist_ok=True)
            # Engine page texts go to a gitignored side file (same convention as
            # .results.json) so a worst-page drill-in never needs a re-extract.
            texts = result.pop("texts")
            (BASELINE_DIR / f"{stem}.json").write_text(
                json.dumps({"meta": meta, **result}, indent=2), encoding="utf-8")
            (BASELINE_DIR / f"{stem}.md").write_text(md, encoding="utf-8")
            (BASELINE_DIR / f"{stem}.pages.json").write_text(
                json.dumps(texts, ensure_ascii=False), encoding="utf-8")
            print(f"wrote evals/baselines/{stem}.{{json,md,pages.json}}")
        return 0

    if args.suite == "extraction":
        print("\n## By kind\n" + extraction_report(result["by_kind"], "kind"))
        print("\n## By doc\n" + extraction_report(result["by_doc"], "doc"))
        meta = {"engine": args.engine, "name": name, "date": date,
                "docs": sorted({p["doc"] for p in result["pages"]}),
                "n_pages": len(result["pages"])}
        if args.gate:
            from evals.extraction import gate

            ref = json.loads(args.gate.read_text(encoding="utf-8"))["pages"]
            regs = gate.page_regressions(result["pages"], ref)
            print(f"\n## Per-page gate vs {args.gate.name}\n" + gate.format_regressions(regs))
            if regs:
                print(f"GATE FAILED: {len(regs)} page metric(s) below the reference")
                return 1
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
        "docs": sorted({d for q in queries for d in query_docs(q)}),
        "n_queries": len(queries), "n_pairs": len({q["pair"] for q in queries}),
        "n_results": args.n_results,
        "corpus_fingerprint": corpus_fingerprint(corpus),
        "git_revision": git_revision(),
        "index": {"mode": "fresh", "pipeline_identity": "engine-managed"},
        "opts": {"rerank": opts.rerank, "hybrid": opts.hybrid,
                 "spell_correction": opts.spell_correction,
                 "variant_expansion": opts.variant_expansion,
                 "extra": _jsonable(opts.extra)},
        "system_tags": _jsonable(SYSTEM_TAGS) if args.engine == "v2" else None,
    }

    if args.gate:
        reference = json.loads(args.gate.read_text(encoding="utf-8"))
        regressions = retrieval_regressions(result, reference)
        print(f"\n## Retrieval gate vs {args.gate.name}\n" + format_retrieval_regressions(regressions))
        if regressions:
            print(f"GATE FAILED: {len(regressions)} headline scope metric(s) below the reference")
            return 1

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

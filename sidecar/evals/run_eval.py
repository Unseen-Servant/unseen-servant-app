"""Run the retrieval eval harness against the production search path.

One command, from sidecar/:

    uv run python -m evals.run_eval

Indexes the eval corpus (once — reruns reuse the persisted index) with the
production indexing pipeline into a dedicated ChromaDB under
``evals/.eval_data``, runs every query in ``evals/queries.yaml`` through
the production ``/api/search`` endpoint (rerank on, production defaults),
judges each result against the answer-chunk ground truth, and prints
nDCG@10, MRR@5, precision@k, and recall@k per query category.

Requires Ollama running locally with the ``bge-m3`` model (same as
production indexing). The corpus is the three CC-licensed rulebooks the
ground truth was authored against — see evals/README.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import yaml

EVALS_DIR = Path(__file__).parent
sys.path.insert(0, str(EVALS_DIR.parent))  # so `python -m evals.run_eval` sees server.py

from evals import scorer
from server import (
    COLLECTION_METADATA,
    build_ollama_embedding_function,
    create_app,
    load_manifest,
)

QUERIES_PATH = EVALS_DIR / "queries.yaml"
DEFAULT_DATA_DIR = EVALS_DIR / ".eval_data"
DEFAULT_CORPUS = Path.home() / "code/unseen-legend-lore-experiments/chunker_spike/corpus"

# The ground truth in queries.yaml is authored against exactly these books.
EXPECTED_PDFS = [
    "Basic-Fantasy-RPG-Rules-r142.pdf",
    "Black-Flag-Roleplaying.pdf",
    "SRD_CC_v5.1.pdf",
]

TOP_K = 10  # nDCG@10 needs 10 results


def build_client(data_dir: Path):
    from fastapi.testclient import TestClient

    data_dir.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(data_dir))
    embedding_function = build_ollama_embedding_function()
    collection = chroma_client.get_or_create_collection(
        name="ttrpg_docs",
        embedding_function=embedding_function,
        metadata=COLLECTION_METADATA,
    )
    app = create_app(
        collection=collection,
        data_dir=data_dir,
        chroma_client=chroma_client,
        embedding_function=embedding_function,
    )
    return TestClient(app)


def ensure_indexed(client, corpus_dir: Path, data_dir: Path) -> None:
    missing = [n for n in EXPECTED_PDFS if not (corpus_dir / n).exists()]
    if missing:
        raise SystemExit(
            f"corpus dir {corpus_dir} is missing {missing} — "
            f"pass --corpus pointing at the eval corpus (see evals/README.md)"
        )
    manifest = load_manifest(data_dir)
    to_index = [
        str(corpus_dir / n)
        for n in EXPECTED_PDFS
        if str(corpus_dir / n) not in manifest.files
    ]
    if not to_index:
        print(f"corpus already indexed ({len(manifest.files)} files)")
        return
    print(f"indexing {len(to_index)} PDFs with the production pipeline (Ollama bge-m3)...")
    resp = client.post("/api/index-files", json={"paths": to_index})
    resp.raise_for_status()
    body = resp.json()
    if body["errors"]:
        raise SystemExit(f"indexing failed: {body['errors']}")
    print(f"indexed {body['indexed']}/{body['total']} PDFs")


def run(
    client, queries: list[dict], rerank: bool, hybrid: bool,
    spell_correction: bool,
) -> list[dict]:
    per_query = []
    for q in queries:
        payload = {
            "query": q["text"],
            "n_results": TOP_K,
            "search_all": True,
            "rerank": rerank,
            "hybrid": hybrid,
            "spell_correction": spell_correction,
        }
        if q["source"] not in (None, "", "any"):
            payload["source_filter"] = next(
                n for n in EXPECTED_PDFS if n.startswith(q["source"])
            )
        resp = client.post("/api/search", json=payload)
        resp.raise_for_status()
        results = resp.json()["results"]
        rels = [scorer.is_relevant(r, q) for r in results]
        per_query.append({
            "text": q["text"],
            "category": q["category"],
            "metrics": scorer.score_query(rels),
            "relevance": [int(r) for r in rels],
            "results": [
                {
                    "filename": r["filename"],
                    "pages": f"{r['page_start']}-{r['page_end']}",
                    "section_heading": r["section_heading"],
                    "relevance_score": r["relevance"],
                    "tier": r["tier"],
                }
                for r in results
            ],
        })
        first_hit = rels.index(True) + 1 if True in rels else "-"
        print(f"  [{q['category']:<12}] first_hit@{first_hit!s:>2}  {q['text']}")
    return per_query


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--no-rerank", action="store_true",
                    help="disable the reranker (production default is on)")
    ap.add_argument("--hybrid", action="store_true",
                    help="fuse BM25 into the candidate pool via RRF "
                         "(experimental /api/search hybrid flag)")
    ap.add_argument("--spell-correction", action="store_true",
                    help="rewrite OOV query tokens to the closest library "
                         "term before embedding (experimental /api/search "
                         "spell_correction flag)")
    ap.add_argument("--write-baseline", metavar="NAME",
                    help="write evals/baselines/NAME.json and NAME.md")
    args = ap.parse_args()

    queries = yaml.safe_load(QUERIES_PATH.read_text())["queries"]
    print(f"loaded {len(queries)} queries from {QUERIES_PATH.name}")

    client = build_client(args.data_dir)
    ensure_indexed(client, args.corpus, args.data_dir)

    rerank = not args.no_rerank
    spell_correction = args.spell_correction
    print(
        f"running {len(queries)} queries "
        f"(rerank={'on' if rerank else 'off'}, "
        f"retrieval={'hybrid' if args.hybrid else 'dense'}, "
        f"spell_correction={'on' if spell_correction else 'off'})..."
    )
    per_query = run(client, queries, rerank, args.hybrid, spell_correction)
    summary = scorer.aggregate(per_query)

    report = scorer.format_report(summary)
    print("\n=== Retrieval metrics (answer-chunk graded) ===")
    print(report)

    if args.write_baseline:
        out_dir = EVALS_DIR / "baselines"
        out_dir.mkdir(exist_ok=True)
        meta = {
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rerank": rerank,
            "retrieval": "hybrid" if args.hybrid else "dense",
            "spell_correction": spell_correction,
            "corpus": EXPECTED_PDFS,
            "queries": len(queries),
            "top_k": TOP_K,
        }
        json_path = out_dir / f"{args.write_baseline}.json"
        json_path.write_text(json.dumps(
            {"meta": meta, "summary": summary, "per_query": per_query},
            indent=2, ensure_ascii=False,
        ) + "\n")
        md_path = out_dir / f"{args.write_baseline}.md"
        md_path.write_text(
            f"# Retrieval eval baseline — {meta['date']}\n\n"
            f"Corpus: {', '.join(EXPECTED_PDFS)}\n"
            f"Queries: {len(queries)} (graded on the specific answer chunk)\n"
            f"Rerank: {'on' if rerank else 'off'}\n"
            f"Retrieval: {meta['retrieval']}\n"
            f"Spell correction: {'on' if spell_correction else 'off'}\n\n"
            "```\n" + report + "\n```\n"
        )
        print(f"\nwrote {json_path.relative_to(EVALS_DIR.parent)} and {md_path.relative_to(EVALS_DIR.parent)}")


if __name__ == "__main__":
    main()

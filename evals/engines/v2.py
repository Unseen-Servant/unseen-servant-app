"""V2 engine — the production ``sidecar/`` pipeline, driven in-process.

Ports the approach of ``sidecar/evals/run_eval.py``: build the real
library store + Ollama embedder against a dedicated data dir, call
the production ``create_app()``, and drive it through FastAPI's
``TestClient`` — the production ``/api/search`` path with zero HTTP
transport, so measured latency is the pipeline's own.

Must run under the sidecar's environment (it imports ``server.py`` and
its dependency tree), from the repo root so the top-level ``evals``
package resolves first::

    uv run --project sidecar python -m evals.engines.v2 --help

Requires Ollama running locally with the ``bge-m3`` model, same as
production indexing.

Standalone smoke test (indexes one small corpus PDF, runs one query)::

    uv run --project sidecar python -m evals.engines.v2 \
        --index evals/corpus/year_zero/YZE-Standard-Reference-Document.pdf \
        --query "how does armor reduce damage"
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Sequence

from .base import IndexReport, Page, SearchOptions, SearchResponse, SearchResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_DIR = REPO_ROOT / "sidecar"

# Default lives under evals/ (gitignored alongside the corpus). Separate
# from sidecar/evals/.eval_data so the legacy harness and this one never
# fight over a data dir.
DEFAULT_DATA_DIR = REPO_ROOT / "evals" / ".eval_data" / "v2"


def _import_sidecar():
    """Make ``sidecar/`` importable and import what we need.

    APPEND (never insert) sidecar to sys.path: both the repo root and
    sidecar/ contain a package named ``evals``, and the top-level one —
    this harness — must keep winning the import race. Nothing in
    the sidecar's modules imports ``evals``, so append order is safe.
    """
    if str(SIDECAR_DIR) not in sys.path:
        sys.path.append(str(SIDECAR_DIR))
    try:
        from fastapi.testclient import TestClient
        from legend_lore.service import (
            PIPELINE_VERSION,
            _extract_and_chunk,
            _extract_pdf_pages,
            load_manifest,
        )
        from server import create_app, open_library_store
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            f"v2 engine needs the sidecar environment (missing: {exc}).\n"
            "Run from the repo root as:\n"
            "    uv run --project sidecar python -m evals.engines.v2 ..."
        ) from exc
    return {
        "TestClient": TestClient,
        "PIPELINE_VERSION": PIPELINE_VERSION,
        "_extract_and_chunk": _extract_and_chunk,
        "_extract_pdf_pages": _extract_pdf_pages,
        "create_app": create_app,
        "open_library_store": open_library_store,
        "load_manifest": load_manifest,
    }


class V2Engine:
    """In-process adapter over the production v2 sidecar."""

    name = "v2"

    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self._client = None
        self._mods = None

    # -- lifecycle -----------------------------------------------------

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        mods = self._mods = _import_sidecar()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        app = mods["create_app"](
            store=mods["open_library_store"](self.data_dir),
            data_dir=self.data_dir,
        )
        self._client = mods["TestClient"](app)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def pipeline_identity(self) -> str:
        """What produced the chunks this engine searches — recorded in a
        library-tier baseline, since that index was not built by the run."""
        if self._mods is None:
            self._mods = _import_sidecar()
        return self._mods["PIPELINE_VERSION"]

    # -- indexing ------------------------------------------------------

    def index(self, pdf_paths: Sequence[Path | str]) -> IndexReport:
        client = self._ensure_client()
        paths = [str(Path(p).expanduser().resolve()) for p in pdf_paths]
        missing = [p for p in paths if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(f"corpus PDFs not found: {missing}")

        manifest = self._mods["load_manifest"](self.data_dir)
        to_index = [p for p in paths if p not in manifest.files]
        skipped = len(paths) - len(to_index)
        if not to_index:
            return IndexReport(requested=len(paths), indexed=0, skipped=skipped)

        resp = client.post("/api/index-files", json={"paths": to_index})
        resp.raise_for_status()
        body = resp.json()
        return IndexReport(
            requested=len(paths),
            indexed=body.get("indexed", 0),
            skipped=skipped,
            errors=body.get("errors", []),
        )

    def tag_systems(self, filename: str, tag: str, keywords: list[str]) -> None:
        """Tag an indexed file with a game system through the product's own
        endpoints: create (or update) a custom system carrying the keywords
        that let ``detect_systems_in_query`` recognise it, then stamp the
        file's chunks + manifest entry. Idempotent."""
        client = self._ensure_client()
        body = {"tag": tag, "keywords": list(keywords)}
        resp = client.post("/api/custom-game-systems", json=body)
        if resp.status_code == 409:  # already created by an earlier doc sharing the tag
            resp = client.put(f"/api/custom-game-systems/{tag}", json=body)
        resp.raise_for_status()
        client.post(
            "/api/set-game-systems", json={"filename": filename, "game_systems": [tag]}
        ).raise_for_status()

    # -- extraction ----------------------------------------------------

    def extract(self, pdf_path: Path | str) -> list[Page]:
        """v2's real page extraction (pymupdf4llm + heading promotion +
        furniture stripping) — no store/Ollama needed, just the sidecar env."""
        if self._mods is None:
            self._mods = _import_sidecar()
        path = Path(pdf_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        pages = self._mods["_extract_pdf_pages"](path)
        return [Page(page_number=p.page_number, text=p.markdown) for p in pages]

    def chunks(self, pdf_path: Path | str) -> list[dict]:
        """v2's real chunker output for one PDF (pymupdf4llm → promotion →
        cleanup → structure_aware), no store/Ollama. What breadcrumb-qa
        grades: the heading each chunk would carry into the embedding."""
        if self._mods is None:
            self._mods = _import_sidecar()
        path = Path(pdf_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        chunks, _system, _systems, error = self._mods["_extract_and_chunk"](path, None, None)
        if error:
            raise RuntimeError(error)
        return [
            {"section_heading": c.section_heading, "chunk_type": str(c.chunk_type),
             "page_start": c.page_start, "page_end": c.page_end, "chars": len(c.text)}
            for c in chunks
        ]

    # -- search --------------------------------------------------------

    def _request_body(self, query: str, opts: SearchOptions, n_results: int | None = None) -> dict:
        body = {
            "query": query,
            "n_results": n_results if n_results is not None else opts.n_results,
            # Always explicit: pin every knob so persisted search_settings.json
            # can never leak into a measurement (run_eval.py's rule).
            "rerank": opts.rerank,
            "hybrid": opts.hybrid,
            "spell_correction": opts.spell_correction,
            "variant_expansion": opts.variant_expansion,
            "max_context_chars": opts.max_context_chars,
        }
        if opts.source_filter:
            body["source_filter"] = opts.source_filter
        if opts.game_system:
            body["game_system"] = opts.game_system
        if opts.collection:
            body["collection"] = opts.collection
        body.update(opts.extra)
        return body

    def warmup(self, options: SearchOptions | None = None) -> None:
        opts = options or SearchOptions()
        client = self._ensure_client()
        client.post(
            "/api/search", json=self._request_body("warmup", opts, n_results=1)
        ).raise_for_status()

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResponse:
        opts = options or SearchOptions()
        client = self._ensure_client()
        t0 = time.perf_counter()
        resp = client.post("/api/search", json=self._request_body(query, opts))
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()
        results = [
            SearchResult(
                text=r.get("text", ""),
                filename=r.get("filename", ""),
                source=r.get("source", ""),
                section_heading=r.get("section_heading", "") or "",
                page_start=r.get("page_start"),
                page_end=r.get("page_end"),
                relevance=float(r.get("relevance", 0.0)),
                tier=r.get("tier", ""),
                reranked=bool(r.get("reranked", False)),
                raw=r,
                matched_text=r.get("matched_text", "") or "",
                also_in=r.get("also_in", []),
            )
            for r in data.get("results", [])
        ]
        return SearchResponse(
            results=results,
            latency_ms=round(latency_ms, 1),
            corrected_query=data.get("corrected_query"),
            message=data.get("message"),
        )


# -- standalone smoke test --------------------------------------------


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--index", type=Path, nargs="*", default=[],
                    help="PDF paths to index before searching")
    ap.add_argument("--query", action="append", default=[],
                    help="query to run (repeatable)")
    ap.add_argument("--n-results", type=int, default=SearchOptions.n_results)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--hybrid", action="store_true")
    ap.add_argument("--no-spell-correction", action="store_true")
    args = ap.parse_args()

    engine = V2Engine(data_dir=args.data_dir)
    opts = SearchOptions(
        n_results=args.n_results,
        rerank=not args.no_rerank,
        hybrid=args.hybrid,
        spell_correction=not args.no_spell_correction,
    )

    if args.index:
        report = engine.index(args.index)
        print(f"index: requested={report.requested} indexed={report.indexed} "
              f"skipped={report.skipped} errors={report.errors or 'none'}")

    if args.query:
        print("warmup (untimed, absorbs lazy model/vocab loads)...")
        engine.warmup(opts)
        for q in args.query:
            resp = engine.search(q, opts)
            print(f"\n'{q}'  →  {len(resp.results)} results in {resp.latency_ms:.0f}ms"
                  f"  payload={resp.payload_chars} chars"
                  + (f"  corrected→'{resp.corrected_query}'" if resp.corrected_query else ""))
            if resp.message:
                print(f"  message: {resp.message}")
            for i, r in enumerate(resp.results[:5], 1):
                pages = f"p.{r.page_start}-{r.page_end}"
                print(f"  {i}. [{r.tier:<6}] {r.relevance:.3f}  "
                      f"{r.filename} {pages}  {r.section_heading[:60]}")
    elif not args.index:
        print("nothing to do — pass --index and/or --query (see --help)")

    engine.close()


if __name__ == "__main__":
    _main()

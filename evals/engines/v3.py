"""V3 engine — drives the sidecar-v3/ pipeline for the Phase 0 harness.

Extraction axis (Phase 2 gate): ``extract(pdf)`` runs the real sidecar-v3
ingestion (Stage A extract → Stage B layout, PP-DocLayout-M ONNX) and returns
per-page text — furniture (`artifact`) and `image` blocks dropped, the rest in
reading order — the same text that feeds indexing. Retrieval (`index`/`search`)
is Phase 3 (query/ not built), so those verbs raise until then.

Runs under the sidecar-v3 environment (its ONNX/apsw/tokenizers deps) — the
engine appends ``sidecar-v3/`` to sys.path, mirroring how v2 appends ``sidecar/``:

    uv run --project sidecar-v3 python -m evals.run_eval --engine v3 --suite extraction
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Sequence

from .base import IndexReport, Page, SearchOptions, SearchResponse, SearchResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_V3 = REPO_ROOT / "sidecar-v3"

# Persistent v3 index — gitignored alongside the corpus, separate from v2's dir.
DEFAULT_DATA_DIR = REPO_ROOT / "evals" / ".eval_data" / "v3"


def _import_v3():
    if str(SIDECAR_V3) not in sys.path:
        sys.path.append(str(SIDECAR_V3))
    try:
        from ingest.extract import extract
        from ingest.layout import LABELS_M, layout
        from ingest.pipeline import index_document, make_layout_fn
        from domain.models import BlockKind
        from index import assets
        from index.store import Store
        from query.pipeline import dense_search
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            f"v3 engine needs the sidecar-v3 environment (missing: {exc}).\n"
            "Run from the repo root as:\n"
            "    uv run --project sidecar-v3 python -m evals.run_eval --engine v3 ..."
        ) from exc
    return {
        "extract": extract, "layout": layout, "LABELS_M": LABELS_M, "BlockKind": BlockKind,
        "assets": assets, "index_document": index_document, "make_layout_fn": make_layout_fn,
        "Store": Store, "dense_search": dense_search,
    }


class V3Engine:
    """In-process adapter over the sidecar-v3 ingestion pipeline."""

    name = "v3"

    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self._mods = None
        self._session = None
        self._embedder = None
        self._store = None
        self._warned_knobs = False

    def _load(self):
        if self._mods is None:
            self._mods = _import_v3()
        return self._mods

    def _layout_session(self):
        if self._session is None:
            self._session = self._load()["assets"].load_layout_session()
        return self._session

    def _ensure_embedder(self):
        if self._embedder is None:
            self._embedder = self._load()["assets"].load_embedder()
        return self._embedder

    def _ensure_store(self):
        if self._store is None:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._store = self._load()["Store"].open(str(self.data_dir / "index.db"))
        return self._store

    def extract(self, pdf_path) -> list[Page]:
        m = self._load()
        BlockKind = m["BlockKind"]
        drop = {BlockKind.artifact, BlockKind.image}
        raw = m["extract"](str(pdf_path))
        blocks = m["layout"](raw, self._layout_session(), m["LABELS_M"])
        by_page: dict[int, list[str]] = {}
        for b in sorted(blocks, key=lambda b: b.reading_order):
            if b.kind not in drop and b.text:
                by_page.setdefault(b.page, []).append(b.text)
        return [Page(page_number=p + 1, text="\n\n".join(by_page.get(p, [])))
                for p in range(raw.page_count)]

    # -- retrieval verbs: Phase 3 rung 1 (dense-only) --

    def index(self, pdf_paths: Sequence) -> IndexReport:
        m = self._load()
        store = self._ensure_store()
        layout_fn = m["make_layout_fn"](self._layout_session())
        embed_fn = self._ensure_embedder().embed
        paths = [Path(p).expanduser().resolve() for p in pdf_paths]
        missing = [str(p) for p in paths if not p.exists()]
        if missing:
            raise FileNotFoundError(f"corpus PDFs not found: {missing}")
        indexed = skipped = 0
        errors: list = []
        for p in paths:
            try:
                rep = m["index_document"](str(p), store, layout_fn, embed_fn, doc_id=p.stem)
                skipped += 1 if rep.skipped else 0
                indexed += 0 if rep.skipped else 1
            except Exception as exc:  # keep going; report the failure
                errors.append({"path": str(p), "error": repr(exc)})
        return IndexReport(requested=len(paths), indexed=indexed, skipped=skipped, errors=errors)

    def _warn_unimplemented(self, opts: SearchOptions) -> None:
        # Ignore unimplemented knobs loudly, once (base.py contract): rung 1 is dense-only.
        if self._warned_knobs:
            return
        pending = [k for k in ("rerank", "hybrid", "spell_correction", "variant_expansion")
                   if getattr(opts, k)]
        if pending:
            print(f"[v3] dense-only rung: ignoring not-yet-built knobs {pending}", file=sys.stderr)
        self._warned_knobs = True

    def warmup(self, options: SearchOptions | None = None) -> None:
        self._ensure_embedder()
        self.search("warmup", options or SearchOptions())

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResponse:
        opts = options or SearchOptions()
        self._warn_unimplemented(opts)
        m = self._load()
        store, embedder = self._ensure_store(), self._ensure_embedder()
        t0 = time.perf_counter()
        rows = m["dense_search"](store, embedder.embed, query, k=opts.n_results)
        latency_ms = (time.perf_counter() - t0) * 1000
        results = [
            SearchResult(
                text=r.get("text", ""),
                filename=r.get("filename", ""),
                source=r.get("source", ""),
                section_heading=r.get("section_heading", "") or "",
                page_start=r.get("page_start"),
                page_end=r.get("page_end"),
                relevance=float(r.get("relevance", 0.0)),
                tier="dense",          # single tier until the calibration rung
                reranked=False,
                raw=r,
            )
            for r in rows
        ]
        return SearchResponse(results=results, latency_ms=round(latency_ms, 1))

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

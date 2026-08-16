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
from pathlib import Path
from typing import Sequence

from .base import IndexReport, Page, SearchOptions, SearchResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_V3 = REPO_ROOT / "sidecar-v3"


def _import_v3():
    if str(SIDECAR_V3) not in sys.path:
        sys.path.append(str(SIDECAR_V3))
    try:
        from ingest.extract import extract
        from ingest.layout import LABELS_M, layout
        from domain.models import BlockKind
        from index import assets
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            f"v3 engine needs the sidecar-v3 environment (missing: {exc}).\n"
            "Run from the repo root as:\n"
            "    uv run --project sidecar-v3 python -m evals.run_eval --engine v3 ..."
        ) from exc
    return extract, layout, LABELS_M, BlockKind, assets


class V3Engine:
    """In-process adapter over the sidecar-v3 ingestion pipeline."""

    name = "v3"

    def __init__(self):
        self._mods = None
        self._session = None

    def _load(self):
        if self._mods is None:
            self._mods = _import_v3()
        return self._mods

    def _layout_session(self):
        if self._session is None:
            *_, assets = self._load()
            self._session = assets.load_layout_session()
        return self._session

    def extract(self, pdf_path) -> list[Page]:
        extract, layout, LABELS_M, BlockKind, _ = self._load()
        drop = {BlockKind.artifact, BlockKind.image}
        raw = extract(str(pdf_path))
        blocks = layout(raw, self._layout_session(), LABELS_M)
        by_page: dict[int, list[str]] = {}
        for b in sorted(blocks, key=lambda b: b.reading_order):
            if b.kind not in drop and b.text:
                by_page.setdefault(b.page, []).append(b.text)
        return [Page(page_number=p + 1, text="\n\n".join(by_page.get(p, [])))
                for p in range(raw.page_count)]

    # -- retrieval verbs: Phase 3 (query/ pipeline) --
    def index(self, pdf_paths: Sequence) -> IndexReport:
        raise SystemExit("v3 retrieval is Phase 3 (query/ not built); the extraction suite works today.")

    def warmup(self, options: SearchOptions | None = None) -> None:
        pass

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResponse:
        raise SystemExit("v3 retrieval is Phase 3 (query/ not built).")

    def close(self) -> None:
        pass

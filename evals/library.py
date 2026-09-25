"""The local-only library tier (roadmap 2026-09-02 §4 Phase 0.4).

The committed corpus (7 CC/OGL books) cannot create the regime a real
library does — hundreds of topically adjacent candidates — and real books
cannot be committed. So the tier pins each book by the SHA-256 the v2
sidecar already stores in ``index_manifest.json`` (``content_hash``) and
resolves it against a v2 data dir at run time. Nothing is indexed by the
harness; the app's own index is read. A query whose book is not in that
index is skipped and reported, so the same YAML runs on any machine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

LIBRARY_PATH = Path(__file__).resolve().parent / "retrieval" / "library.yaml"
MANIFEST_FILENAME = "index_manifest.json"   # sidecar/legend_lore/service.py MANIFEST_FILENAME


@dataclass(frozen=True)
class LibraryDoc:
    id: str
    pdf_path: Path
    pdf_sha256: str
    system: str
    ref_digest: str | None = None   # no digital-native reference for a real book


@dataclass(frozen=True)
class LibraryCorpus:
    documents: list[LibraryDoc]


def load_library(path: Path = LIBRARY_PATH) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    docs = raw.get("docs") or []
    queries = raw.get("queries") or []
    seen: set[str] = set()
    for d in docs:
        if d["id"] in seen:
            raise ValueError(f"duplicate doc id {d['id']!r} in {path.name}")
        seen.add(d["id"])
        if len(d["sha256"]) != 64:
            raise ValueError(f"doc {d['id']!r}: sha256 must be 64 hex chars")
    return {"docs": docs, "queries": queries}


def manifest_files(data_dir: Path) -> dict[str, dict]:
    """``{absolute pdf path: manifest entry}`` from a v2 data dir."""
    p = Path(data_dir) / MANIFEST_FILENAME
    if not p.exists():
        raise FileNotFoundError(f"no {MANIFEST_FILENAME} in {data_dir} — is this a v2 data dir?")
    return json.loads(p.read_text(encoding="utf-8")).get("files", {})


def resolve(library: dict, files: dict[str, dict]) -> tuple[LibraryCorpus, list[str]]:
    """Map library docs onto indexed files by content hash."""
    by_hash = {e.get("content_hash"): (path, e) for path, e in files.items() if e.get("content_hash")}
    docs: list[LibraryDoc] = []
    missing: list[str] = []
    for d in library["docs"]:
        hit = by_hash.get(d["sha256"])
        if hit is None:
            missing.append(d["id"])
            continue
        path, _ = hit
        docs.append(LibraryDoc(id=d["id"], pdf_path=Path(path), pdf_sha256=d["sha256"],
                               system=d.get("title", d["id"])))
    return LibraryCorpus(documents=docs), missing


def select_queries(queries: list[dict], present: set[str]) -> tuple[list[dict], list[str]]:
    """Queries whose every doc is present. ``doc`` must always name a declared
    book — for an uncued query it is the representative used for anchor
    verification (same rule as queries.yaml; ``any`` is not accepted here)."""
    kept: list[dict] = []
    skipped: list[str] = []
    for q in queries:
        doc = q["doc"]
        needed = list(doc) if isinstance(doc, list) else [doc]
        if all(d in present for d in needed):
            kept.append(q)
        else:
            skipped.append(q["id"])
    return kept, skipped

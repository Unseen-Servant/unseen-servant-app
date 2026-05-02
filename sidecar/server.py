"""
Legend Lore — ChromaDB indexing sidecar.

Started automatically by the Tauri desktop app.
Provides HTTP endpoints for indexing PDFs and searching indexed content.

Usage:
    python server.py --port 8420 --data-dir /path/to/app/data
"""

import argparse
import hashlib
import json
import os
import re
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
import pymupdf
import pymupdf4llm
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from chunker import (
    CHUNKER_VERSION,
    EMBEDDING_MODEL,
    Chunk,
    PageMarkdown,
    structure_aware,
)
from cleanup import clean_pages
from promote_headings import promote_markdown
from granularity import EmbedUnit, ParentDoc, build as build_granularity
from parents_store import (
    upsert_parents, fetch_parents, delete_parents_for_source,
    clear_all_parents,
)


# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Legend Lore indexing sidecar")
    parser.add_argument("--port", type=int, default=8420, help="HTTP port")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Directory for ChromaDB storage (default: ./chroma_db)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pure helpers (no dependencies — safe to import in tests)
# ---------------------------------------------------------------------------

from game_systems import GAME_SYSTEMS, KNOWN_SYSTEMS

import unicodedata


def _normalize_for_match(s: str) -> str:
    """Lowercase, decompose accents, fold ``&`` to ``n``, drop non-alphanum.

    The goal is that a keyword like ``"d&d 5e"`` matches paths or content
    written as ``"D&D 5E"``, ``"DnD 5e"``, ``"d&d-5e"``, ``"dnd_5e"``, or
    ``"Mörk Borg"`` all the same. Both the haystack and the needle go
    through this helper before substring matching.
    """
    # NFKD splits ``ö`` into ``o`` + combining diaeresis; the combining
    # codepoint is then dropped along with all other non-alphanum below.
    s = unicodedata.normalize("NFKD", s).lower()
    # ``d&d`` and ``dnd`` collide cleanly when ``&`` becomes ``n``.
    s = s.replace("&", "n")
    return "".join(ch for ch in s if ch.isalnum())


def detect_game_systems(
    pdf_path: Path,
    text: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> list[str]:
    """Detect all matching TTRPG game systems from folder path or PDF content.

    Detection priority:
    1. Folder name match (user's deliberate organization)
    2. Content keyword match (first 2000 chars of extracted text)
    3. Empty list when nothing matches.

    Both haystack (path/text) and keywords are normalized via
    ``_normalize_for_match`` before substring matching, so case,
    whitespace, punctuation (``&``, ``-``, ``_``, ``.``), and accents
    are ignored.

    Returns matches in ``KNOWN_SYSTEMS`` insertion order, deduped. Path
    matches take precedence over content matches: a path hit blocks the
    content scan from contributing the same tag a second time, but a tag
    that only appears in content is still included.

    Args:
        known_systems: Optional tag→keywords dict. When None, uses the
            module-level KNOWN_SYSTEMS (built-in only). Pass a merged dict
            to include user-defined custom systems in detection.
    """
    systems = known_systems if known_systems is not None else KNOWN_SYSTEMS
    hits: list[str] = []
    seen: set[str] = set()

    path_norm = _normalize_for_match(str(pdf_path))
    for system, keywords in systems.items():
        if any(_normalize_for_match(k) in path_norm for k in keywords if k):
            if system not in seen:
                hits.append(system)
                seen.add(system)

    if text:
        text_norm = _normalize_for_match(text[:2000])
        for system, keywords in systems.items():
            if system in seen:
                continue
            if any(_normalize_for_match(k) in text_norm for k in keywords if k):
                hits.append(system)
                seen.add(system)

    return hits


def detect_game_system(
    pdf_path: Path,
    text: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> str:
    """Detect the primary TTRPG game system (first match) or ``"unknown"``."""
    hits = detect_game_systems(pdf_path, text, known_systems)
    return hits[0] if hits else "unknown"


_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _flatten_br_packed_cells(md: str) -> str:
    """Expand <br>-packed table rows into separate rows.

    pymupdf4llm preserves visually-stacked cells (common in stat blocks:
    "Armor Class:" / "Hit Dice:" sharing a label column) by joining rows
    with <br> inside a single Markdown cell. When the <br> counts in two
    or more cells of a row match, split the row into one row per pair.
    Rows with mismatched counts are legitimate multi-line content and
    pass through unchanged so we never lose data.
    """
    out = []
    for line in md.split("\n"):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2):
            out.append(line)
            continue
        # Strip exactly one leading and trailing "|" so empty edge cells survive.
        cells = [c.strip() for c in stripped[1:-1].split("|")]
        counts = [len(_BR_RE.findall(c)) for c in cells]
        non_zero = [n for n in counts if n > 0]
        if len(non_zero) >= 2 and len(set(non_zero)) == 1:
            n = non_zero[0]
            parts = [_BR_RE.split(c) if cnt else [c] * (n + 1)
                     for c, cnt in zip(cells, counts)]
            for row in zip(*parts):
                out.append("|" + "|".join(p.strip() for p in row) + "|")
        else:
            out.append(line)
    return "\n".join(out)


def _extract_spans(page: pymupdf.Page) -> list[dict]:
    """Per-page font-span side-channel for heading-hierarchy promotion.

    pymupdf flag bits used: 16 = bold, 2 = italic. Sizes rounded to
    2 decimals (matches the spike's signature granularity).
    """
    raw = page.get_text("dict")
    spans: list[dict] = []
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                flags = int(span.get("flags", 0))
                spans.append({
                    "text": text,
                    "size": round(float(span.get("size", 0.0)), 2),
                    "bold": bool(flags & 16),
                    "italic": bool(flags & 2),
                })
    return spans


def _extract_toc(doc: pymupdf.Document) -> dict:
    """Document outline (bookmark tree) for TOC-based heading promotion.

    Returns ``{"n_entries", "max_depth", "entries"}`` where ``entries``
    is ``[[level, title, page1], ...]`` per ``Document.get_toc(simple=True)``.
    Empty entries=[] when the PDF has no outline; promotion falls back
    to font_cluster cleanly in that case.
    """
    toc = doc.get_toc(simple=True)
    if not toc:
        return {"n_entries": 0, "max_depth": 0, "entries": []}
    return {
        "n_entries": len(toc),
        "max_depth": max(entry[0] for entry in toc),
        "entries": toc,
    }


def _extract_pdf_pages(pdf_path: Path) -> list[PageMarkdown]:
    """Extract a PDF page-by-page as Markdown via pymupdf4llm.

    Pipeline (issue #157 — heading-hierarchy promotion adoption):
      pymupdf4llm.to_markdown  +  font-span side-channel  +  TOC
        → promote_headings (toc_then_font; TOC capped at depth 1)
        → R1 (rejoin CR fragments)
        → R3 (strip image-placeholder chrome)
        → R4 (strip running-heading chrome — cross-page detection)
        → R2 (strip running paragraph headers/footers — cross-page)
        → _flatten_br_packed_cells (atomic-table preservation for the
          structure-aware chunker)

    pymupdf (opened via `fitz`/`pymupdf.open`) also accepts
    .txt/.epub/.xps/.cbz silently; restrict to PDFs to match the
    documented API surface.

    OCR is disabled (`use_ocr=False`): pymupdf4llm otherwise runs Tesseract
    on any page whose text layer it deems unreliable, which dominates
    extraction time on large PDFs. TTRPG rulebooks are overwhelmingly
    digital-native, so the cost rarely buys anything. Scanned or
    OCR-needing PDFs will index with empty/sparse text on those pages.
    """
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF: {pdf_path.name}")
    raw_pages: list[tuple[int, str]] = []
    spans_pages: list[dict] = []
    with pymupdf.open(pdf_path) as doc:
        toc = _extract_toc(doc)
        for i in range(doc.page_count):
            md = pymupdf4llm.to_markdown(doc, pages=[i], show_progress=False, use_ocr=False)
            if md:
                page_no = i + 1
                raw_pages.append((page_no, md))
                spans_pages.append({
                    "page_number": page_no,
                    "spans": _extract_spans(doc.load_page(i)),
                })
    if not raw_pages:
        return []
    pages_dict = [{"page_number": pn, "markdown": md} for pn, md in raw_pages]
    promoted, promo_report = promote_markdown(
        pages_dict, spans_pages, toc, strategy="toc_then_font"
    )
    print(
        f"[promote] {pdf_path.name}: "
        f"strategy={promo_report['strategy']} "
        f"n_headings={promo_report['n_headings']} "
        f"toc_used={promo_report['toc_used']} "
        f"font_used={promo_report['font_used']} "
        f"fallback={promo_report['fallback_count']} "
        f"distribution={promo_report['promoted_level_distribution']}"
    )
    cleaned, report = clean_pages([p["markdown"] for p in promoted])
    print(f"[cleanup] {pdf_path.name}: {report.summary()}")
    return [
        PageMarkdown(page_number=pn, markdown=_flatten_br_packed_cells(md))
        for (pn, _), md in zip(raw_pages, cleaned)
    ]


def _extract_pdf_text(pdf_path: Path) -> str:
    """Flat-string view of the PDF — used by game-system detection."""
    return "\n\n".join(p.markdown for p in _extract_pdf_pages(pdf_path))


def file_content_hash(path: Path) -> str:
    """Compute SHA-256 hash of file contents. Reads in 64KB chunks for memory efficiency."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class IndexFilesRequest(BaseModel):
    paths: list[str]
    game_system: str | None = None

class ReindexFileRequest(BaseModel):
    path: str
    game_system: str | None = None

class IndexStatusRequest(BaseModel):
    selected_paths: list[str]

class SyncIndexRequest(BaseModel):
    selected_paths: list[str]
    game_system_overrides: dict[str, str] | None = None
    force: bool = False

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    source_filter: str | None = None
    game_system: str | None = None
    game_systems: list[str] | None = None
    collection: str | None = None
    source_paths: list[str] | None = None
    search_all: bool = False

class SetGameSystemRequest(BaseModel):
    filename: str
    game_system: str

class SetGameSystemsRequest(BaseModel):
    filename: str
    game_systems: list[str]

class CustomGameSystemRequest(BaseModel):
    tag: str
    keywords: list[str] = []
    color: str | None = None

class ToggleBuiltinRequest(BaseModel):
    tag: str
    disabled: bool

class CreateCollectionRequest(BaseModel):
    name: str
    file_paths: list[str]
    description: str = ""
    color: str | None = None

class UpdateCollectionRequest(BaseModel):
    file_paths: list[str] | None = None
    description: str | None = None
    color: str | None = None
    archived: bool | None = None
    last_used_at: str | None = None

class SetActiveContextRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Index manifest — tracks what's been indexed and when
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "index_manifest.json"


class ManifestEntry(BaseModel):
    filename: str
    mtime: float
    chunk_count: int
    indexed_at: str
    game_system: str = "unknown"
    game_systems: list[str] = []
    content_hash: str = ""
    file_size: int = 0

    def model_post_init(self, __context):
        # Backfill on load for entries written before multi-tag support.
        if not self.game_systems and self.game_system != "unknown":
            self.game_systems = [self.game_system]


class IndexManifest(BaseModel):
    version: int = 1
    files: dict[str, ManifestEntry] = {}


def load_manifest(data_dir: Path) -> IndexManifest:
    """Load the index manifest from disk, or return an empty one."""
    manifest_path = data_dir / MANIFEST_FILENAME
    if manifest_path.exists():
        raw = json.loads(manifest_path.read_text())
        return IndexManifest(**raw)
    return IndexManifest()


def save_manifest(data_dir: Path, manifest: IndexManifest) -> None:
    """Write the index manifest to disk atomically."""
    manifest_path = data_dir / MANIFEST_FILENAME
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(manifest.model_dump_json(indent=2))
    os.replace(tmp_path, manifest_path)


# ---------------------------------------------------------------------------
# Collections — named subsets of indexed files
# ---------------------------------------------------------------------------

COLLECTIONS_FILENAME = "collections.json"
COLLECTIONS_STORE_VERSION = 2


class Collection(BaseModel):
    id: str
    name: str
    file_paths: list[str]
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    description: str = ""
    color: str | None = None
    archived: bool = False


class CollectionsStore(BaseModel):
    version: int = COLLECTIONS_STORE_VERSION
    collections: dict[str, Collection] = {}
    active_context: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_collection_record(name: str, raw: dict) -> dict:
    """Fill in v2 fields for an on-disk record. v1 records get sensible defaults."""
    created_at = raw.get("created_at") or _now_iso()
    return {
        "id": raw.get("id") or str(uuid.uuid4()),
        "name": raw.get("name") or name,
        "file_paths": raw.get("file_paths", []),
        "created_at": created_at,
        "updated_at": raw.get("updated_at") or created_at,
        "last_used_at": raw.get("last_used_at"),
        "description": raw.get("description", ""),
        "color": raw.get("color"),
        "archived": raw.get("archived", False),
    }


def load_collections(data_dir: Path) -> CollectionsStore:
    """Load collections from disk, migrating legacy records to the current schema."""
    path = data_dir / COLLECTIONS_FILENAME
    if not path.exists():
        return CollectionsStore()
    raw = json.loads(path.read_text())
    raw_collections = raw.get("collections", {})
    migrated = {
        name: _migrate_collection_record(name, c)
        for name, c in raw_collections.items()
    }
    active_context = raw.get("active_context")
    if active_context not in migrated:
        active_context = None
    return CollectionsStore(
        version=COLLECTIONS_STORE_VERSION,
        collections=migrated,
        active_context=active_context,
    )


def save_collections(data_dir: Path, store: CollectionsStore) -> None:
    """Write collections to disk atomically."""
    path = data_dir / COLLECTIONS_FILENAME
    tmp_path = path.with_suffix(".json.tmp")
    store.version = COLLECTIONS_STORE_VERSION
    tmp_path.write_text(store.model_dump_json(indent=2))
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Custom game systems — user-defined systems that merge with built-ins
# ---------------------------------------------------------------------------

CUSTOM_SYSTEMS_FILENAME = "custom_game_systems.json"


class CustomGameSystemEntry(BaseModel):
    tag: str
    keywords: list[str] = []
    color: str | None = None


class CustomGameSystemsStore(BaseModel):
    version: int = 1
    systems: list[CustomGameSystemEntry] = []
    disabled_builtins: list[str] = []


def load_custom_systems(data_dir: Path) -> CustomGameSystemsStore:
    """Load custom game systems from disk, or return an empty store."""
    path = data_dir / CUSTOM_SYSTEMS_FILENAME
    if path.exists():
        raw = json.loads(path.read_text())
        return CustomGameSystemsStore(**raw)
    return CustomGameSystemsStore()


def save_custom_systems(data_dir: Path, store: CustomGameSystemsStore) -> None:
    """Write custom game systems to disk atomically."""
    path = data_dir / CUSTOM_SYSTEMS_FILENAME
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(store.model_dump_json(indent=2))
    os.replace(tmp_path, path)


DEFAULT_CUSTOM_COLOR = "#b69f81"  # tan, matches the app accent


def get_merged_systems(
    custom_store: CustomGameSystemsStore,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Merge built-in GAME_SYSTEMS with custom overrides/additions.

    Returns (merged_list, known_systems_dict) where:
    - merged_list: full entries with tag, keywords, color, is_builtin,
      is_customized
    - known_systems_dict: tag → keywords mapping for detect_game_system
    """
    builtin_by_tag = {entry["tag"]: entry for entry in GAME_SYSTEMS}
    custom_tags = {entry.tag for entry in custom_store.systems}
    disabled = set(custom_store.disabled_builtins)

    merged = []
    for entry in GAME_SYSTEMS:
        if entry["tag"] in disabled:
            continue
        if entry["tag"] in custom_tags:
            # Custom entry overrides built-in with same tag
            continue
        merged.append({**entry, "is_builtin": True, "is_customized": False})

    for entry in custom_store.systems:
        is_override = entry.tag in builtin_by_tag
        # Override inherits the built-in color when the user didn't pick one;
        # pure-custom entries fall back to the default app accent.
        if entry.color is not None:
            color = entry.color
        elif is_override:
            color = builtin_by_tag[entry.tag].get("color", DEFAULT_CUSTOM_COLOR)
        else:
            color = DEFAULT_CUSTOM_COLOR
        merged.append({
            "tag": entry.tag,
            "keywords": entry.keywords,
            "color": color,
            "is_builtin": is_override,
            "is_customized": is_override,
        })

    known = {e["tag"]: e["keywords"] for e in merged}
    return merged, known


def resolve_collection_filenames(
    coll: Collection, manifest: IndexManifest
) -> list[str]:
    """Resolve a collection's file_paths to filenames in the manifest.

    Filters out paths no longer indexed (graceful degradation).
    """
    filenames = []
    for file_path in coll.file_paths:
        if file_path in manifest.files:
            filenames.append(manifest.files[file_path].filename)
    return filenames


# ---------------------------------------------------------------------------
# Reusable indexing / deletion helpers
# ---------------------------------------------------------------------------


def chunk_id_prefix(pdf_path: Path) -> str:
    """Return a stable, collision-free prefix for chunk IDs.

    Uses an 8-char hex digest of the full path so that two PDFs with the same
    stem (e.g. ``/5e/Monster Manual.pdf`` and ``/pf2e/Monster Manual.pdf``)
    never collide.
    """
    path_hash = hashlib.sha256(str(pdf_path).encode()).hexdigest()[:8]
    return f"{path_hash}_{pdf_path.stem}"


def _embed_unit_metadata(pdf_path: Path, eu: EmbedUnit, game_system: str) -> dict:
    return {
        "source": str(pdf_path),
        "filename": pdf_path.name,
        "chunk": eu.ordinal,
        "game_system": game_system,
        "chunk_type": eu.chunk_type,
        "section_heading": eu.section_heading or "",
        "page_start": eu.page_start,
        "page_end": eu.page_end,
        "parent_id": eu.parent_id,
        "chunker_version": CHUNKER_VERSION,
        "embedding_model": EMBEDDING_MODEL,
    }


def _embed_text(eu: EmbedUnit) -> str:
    """Heading-prepended text for embedding (storage of eu.text unchanged).

    hybrid_retrieval_spike measured +0.184 MRR@5 / +0.150 recall@5 from this
    one change: embedding sees the section_heading breadcrumb as topical
    context for the embed unit body.
    """
    if eu.section_heading:
        return f"{eu.section_heading}\n\n{eu.text}"
    return eu.text


# Embed batching tunables (issue #158).
# 256 was chosen over the previous 100 to amortize Ollama per-call overhead;
# bge-m3 embeds each input independently so the 8192 ctx applies per input,
# not per batch (mean embed-text size ~400 chars / ~100 tokens). Concurrency=3
# fires up to N embed batches at Ollama in parallel; upserts to Chroma stay
# serial because its SQLite is not concurrent-write friendly.
EMBED_BATCH_SIZE = 256
EMBED_CONCURRENCY = 3


def _embed_batch(collection, batch: list[EmbedUnit]) -> list[list[float]]:
    """Heading-prepended embeddings for a batch (no DB writes)."""
    return collection._embedding_function([_embed_text(eu) for eu in batch])


def _upsert_batch(
    collection,
    batch: list[EmbedUnit],
    embeddings: list[list[float]],
    pdf_path: Path,
    game_system: str,
    prefix: str,
) -> None:
    """Upsert a pre-embedded batch with stored text and metadata."""
    collection.upsert(
        embeddings=embeddings,
        documents=[eu.text for eu in batch],
        metadatas=[_embed_unit_metadata(pdf_path, eu, game_system) for eu in batch],
        ids=[f"{prefix}_{eu.ordinal}" for eu in batch],
    )


def _embed_and_upsert_units(
    collection,
    embed_units: list[EmbedUnit],
    pdf_path: Path,
    game_system: str,
    prefix: str,
    batch_size: int = EMBED_BATCH_SIZE,
    concurrency: int = EMBED_CONCURRENCY,
):
    """Embed batches concurrently, upsert serially in submission order.

    Generator that yields each batch's unit count after it's been written to
    Chroma. Callers that don't need progress can `sum(...)` to get the total.
    Submission-order draining keeps chunk ordinals deterministic in the DB
    and progress events monotonic for streaming callers.
    """
    if not embed_units:
        return
    batches = [
        embed_units[i:i + batch_size]
        for i in range(0, len(embed_units), batch_size)
    ]
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(_embed_batch, collection, b) for b in batches]
        for batch, fut in zip(batches, futures):
            embeddings = fut.result()
            _upsert_batch(collection, batch, embeddings, pdf_path, game_system, prefix)
            yield len(batch)


def _index_chunks(
    chunks: list[Chunk],
    pdf_path: Path,
    game_system: str,
    collection,
    data_dir: Path | None,
    batch_size: int = EMBED_BATCH_SIZE,
) -> int:
    """Run the granularity step and persist embed units + parents.

    Splits chunks into ~400-char embed units (tables atomic) and contiguous
    same-breadcrumb parents (capped at 6,000 chars). Embed units go to
    ChromaDB with parent_id in metadata; parents go to the SQLite store.

    Returns the number of embed units upserted.
    """
    if not chunks:
        return 0
    embed_units, parents = build_granularity(chunks)
    if data_dir:
        upsert_parents(data_dir, str(pdf_path), parents)
    prefix = chunk_id_prefix(pdf_path)
    return sum(_embed_and_upsert_units(
        collection, embed_units, pdf_path, game_system, prefix,
        batch_size=batch_size,
    ))


def _extract_and_chunk(
    pdf_path: Path, game_system: str | None,
    known_systems: dict[str, list[str]] | None,
) -> tuple[list[Chunk], str, list[str], str | None]:
    """Shared preamble: extract pages, detect system, run structure_aware.

    Returns (chunks, resolved_system, resolved_systems, error_message).
    ``resolved_system`` is the primary tag (first match) stored in chunk
    metadata; ``resolved_systems`` is the full multi-tag list stored in
    the manifest. When ``game_system`` is provided as an override, the
    list contains just that single tag.
    """
    if not pdf_path.exists():
        return [], "unknown", [], f"{pdf_path.name}: File not found"
    try:
        pages = _extract_pdf_pages(pdf_path)
        if not pages:
            return [], "unknown", [], f"{pdf_path.name}: Empty or scanned PDF"
        flat_text = "\n\n".join(p.markdown for p in pages)
        if not flat_text.strip():
            return [], "unknown", [], f"{pdf_path.name}: Empty or scanned PDF"
        if game_system:
            resolved_system = game_system
            resolved_systems = [game_system]
        else:
            resolved_systems = detect_game_systems(
                pdf_path, flat_text, known_systems=known_systems
            )
            resolved_system = resolved_systems[0] if resolved_systems else "unknown"
        chunks = structure_aware(pages, source_pdf=pdf_path.name)
        return chunks, resolved_system, resolved_systems, None
    except Exception as e:
        return [], "unknown", [], f"{pdf_path.name}: {str(e)}"


def index_single_pdf(
    pdf_path: Path, collection, game_system: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
    data_dir: Path | None = None,
) -> tuple[int, str | None, str, list[str]]:
    """Extract, chunk, and upsert a single PDF into ChromaDB + parents store.

    Returns (embed_unit_count, error_message, game_system, game_systems).
    error_message is None on success.
    """
    chunks, resolved_system, resolved_systems, error = _extract_and_chunk(
        pdf_path, game_system, known_systems
    )
    if error:
        return 0, error, resolved_system, resolved_systems
    count = _index_chunks(chunks, pdf_path, resolved_system, collection, data_dir)
    return count, None, resolved_system, resolved_systems


def prepare_pdf(
    pdf_path: Path, game_system: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> tuple[list[Chunk], str, list[str], str | None]:
    """Extract text and chunk a PDF without upserting.

    Returns (chunks, game_system, game_systems, error_message).
    error_message is None on success.
    """
    return _extract_and_chunk(pdf_path, game_system, known_systems)


def compact_sqlite(data_dir: Path) -> int:
    """VACUUM the ChromaDB and parents SQLite databases.

    Both stores accumulate tombstoned pages on every delete-index or
    re-index cycle; SQLite doesn't reclaim that space without VACUUM.

    Returns total bytes reclaimed across both files (0 if neither exists).
    """
    if not data_dir:
        return 0
    import sqlite3
    reclaimed = 0
    for name in ("chroma.sqlite3", "parents.sqlite3"):
        path = data_dir / name
        if not path.exists():
            continue
        size_before = os.path.getsize(path)
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
        reclaimed += size_before - os.path.getsize(path)
    return reclaimed


# UUID-named segment directories created by Chroma's HNSW persistence.
_UUID_DIR_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _live_segment_ids(data_dir: Path) -> set[str]:
    """Read live segment UUIDs from chroma.sqlite3.

    Returns an empty set if the database doesn't exist (fresh install).
    """
    sqlite_path = data_dir / "chroma.sqlite3"
    if not sqlite_path.exists():
        return set()
    import sqlite3
    conn = sqlite3.connect(str(sqlite_path))
    try:
        rows = conn.execute("SELECT id FROM segments").fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def _segment_ids_for_collection(data_dir: Path, collection_name: str) -> list[str]:
    """Return segment UUIDs belonging to a named Chroma collection."""
    sqlite_path = data_dir / "chroma.sqlite3"
    if not sqlite_path.exists():
        return []
    import sqlite3
    conn = sqlite3.connect(str(sqlite_path))
    try:
        rows = conn.execute(
            "SELECT s.id FROM segments s "
            "JOIN collections c ON s.collection = c.id "
            "WHERE c.name = ?",
            (collection_name,),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def _remove_segment_dir(data_dir: Path, segment_id: str) -> int:
    """Remove a single segment directory if it exists. Returns bytes freed.

    UUID-pattern check guards against rmtree on unrelated paths if Chroma's
    segment id format ever drifts.
    """
    if not _UUID_DIR_RE.match(segment_id):
        return 0
    seg_dir = data_dir / segment_id
    if not seg_dir.is_dir():
        return 0
    import shutil
    size = sum(p.stat().st_size for p in seg_dir.rglob("*") if p.is_file())
    shutil.rmtree(seg_dir, ignore_errors=True)
    return size


def _sqlite_freelist_bytes(sqlite_path: Path) -> int:
    """Return bytes that ``VACUUM`` would reclaim from a SQLite database."""
    if not sqlite_path.exists():
        return 0
    import sqlite3
    conn = sqlite3.connect(str(sqlite_path))
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
    finally:
        conn.close()
    return page_size * freelist


def _orphan_segment_bytes(data_dir: Path) -> int:
    """Return total bytes in UUID-named segment dirs not referenced by any
    live segment. Read-only counterpart of ``gc_orphan_segments``.
    """
    if not data_dir or not data_dir.is_dir():
        return 0
    live = _live_segment_ids(data_dir)
    total = 0
    for entry in data_dir.iterdir():
        if not entry.is_dir() or not _UUID_DIR_RE.match(entry.name):
            continue
        if entry.name in live:
            continue
        total += sum(p.stat().st_size for p in entry.rglob("*") if p.is_file())
    return total


def _compute_reclaimable_bytes(data_dir: Path | None) -> int:
    """Bytes that ``/api/compact`` would reclaim if invoked right now.

    Sum of: chroma.sqlite3 freelist + parents.sqlite3 freelist + orphan
    segment dir bytes. Powers the UI's gating on whether to surface the
    Compact button.
    """
    if not data_dir:
        return 0
    return (
        _sqlite_freelist_bytes(data_dir / "chroma.sqlite3")
        + _sqlite_freelist_bytes(data_dir / "parents.sqlite3")
        + _orphan_segment_bytes(data_dir)
    )


def gc_orphan_segments(data_dir: Path) -> int:
    """Remove UUID-named segment directories not referenced by any live segment.

    Chroma's ``delete_collection`` only removes metadata rows from
    ``chroma.sqlite3``; the on-disk segment directories are left behind.
    Each call to ``/api/delete-index`` therefore leaks ~250 MB on a typical
    library. This helper walks ``data_dir`` for UUID-named directories and
    removes any whose UUID is not in ``segments.id``.

    Returns bytes reclaimed.
    """
    if not data_dir or not data_dir.is_dir():
        return 0
    live = _live_segment_ids(data_dir)
    reclaimed = 0
    for entry in data_dir.iterdir():
        if not entry.is_dir():
            continue
        if not _UUID_DIR_RE.match(entry.name):
            continue
        if entry.name in live:
            continue
        reclaimed += _remove_segment_dir(data_dir, entry.name)
    return reclaimed


def delete_source_chunks(
    source_path: str, collection, data_dir: Path | None = None
) -> int:
    """Delete all chunks for a given source path from ChromaDB.

    Uses the full ``source`` metadata field to avoid collisions when two PDFs
    share the same filename in different directories. Also drops the source's
    parent rows from the parents store so re-indexes don't accumulate orphans.

    Returns the number of deleted chunks, or 0 if not found.
    """
    results = collection.get(where={"source": source_path}, include=[])
    ids_to_delete = results["ids"]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)

    if data_dir:
        delete_parents_for_source(data_dir, source_path)

    return len(ids_to_delete)


def compute_diff(
    selected_paths: list[str], manifest: IndexManifest
) -> dict[str, list[dict]]:
    """Compare selected paths against the manifest to find what changed.

    Returns a dict with keys: to_add, to_remove, to_rename, to_update,
    up_to_date, errors.  Each value is a list of dicts describing the file.

    Pure diff — does not factor in user intent like "reindex everything."
    Callers wanting to force-reprocess unchanged files should promote
    ``up_to_date`` into ``to_update`` themselves (see ``_sync_core``).
    """
    selected = set(selected_paths)
    indexed = set(manifest.files.keys())

    to_add = []
    to_update = []
    up_to_date = []
    errors = []
    missing_indexed: list[tuple[str, ManifestEntry]] = []

    stale_paths: list[str] = []

    for path_str in selected:
        path = Path(path_str)
        if path_str not in indexed:
            # New file — not yet indexed
            if not path.exists():
                # Stale selection — file never indexed and doesn't exist.
                # Not an error; frontend should drop this path from selections.
                stale_paths.append(path_str)
            else:
                to_add.append({"path": path_str, "filename": path.name})
        else:
            # Already indexed — check if modified
            entry = manifest.files[path_str]
            if not path.exists():
                # Defer — might be a rename; we'll scan the parent dir below
                missing_indexed.append((path_str, entry))
            else:
                current_mtime = os.path.getmtime(path_str)
                if current_mtime != entry.mtime:
                    to_update.append({
                        "path": path_str,
                        "filename": path.name,
                        "chunk_count": entry.chunk_count,
                        "game_system": entry.game_system,
                        "game_systems": list(entry.game_systems),
                        "indexed_at": entry.indexed_at,
                    })
                else:
                    up_to_date.append({
                        "path": path_str,
                        "filename": path.name,
                        "chunk_count": entry.chunk_count,
                        "game_system": entry.game_system,
                        "game_systems": list(entry.game_systems),
                        "indexed_at": entry.indexed_at,
                    })

    # --- Resolve missing indexed files ---
    # For each missing file, check if its parent directory is accessible.
    # If so, scan for a rename candidate (same content hash). If no rename
    # is found, the file was genuinely deleted → auto-remove from index.
    # If the parent is inaccessible (e.g. unmounted drive), keep as error.
    to_remove: list[dict] = []
    to_auto_remove: list[dict] = []
    for path_str, entry in missing_indexed:
        parent = Path(path_str).parent
        if not parent.is_dir():
            # Parent inaccessible — possible unmounted drive, keep as error
            errors.append({"path": path_str, "error": "File not found on disk"})
            continue

        # Try rename detection if we have a content hash
        found_rename = False
        if entry.content_hash:
            try:
                for candidate in parent.iterdir():
                    if candidate.suffix.lower() != ".pdf":
                        continue
                    cand_str = str(candidate)
                    if cand_str in selected or cand_str in indexed:
                        continue  # already tracked
                    try:
                        if candidate.stat().st_size != entry.file_size:
                            continue
                    except OSError:
                        continue
                    if file_content_hash(candidate) == entry.content_hash:
                        # Match! Route through rename detection pipeline.
                        to_remove.append({
                            "path": path_str,
                            "filename": entry.filename,
                            "chunk_count": entry.chunk_count,
                            "game_system": entry.game_system,
                            "game_systems": list(entry.game_systems),
                        })
                        to_add.append({"path": cand_str, "filename": candidate.name})
                        found_rename = True
                        break
            except OSError:
                pass

        if not found_rename:
            # Parent accessible, file gone, no rename match → auto-remove
            to_auto_remove.append({
                "path": path_str,
                "filename": entry.filename,
                "chunk_count": entry.chunk_count,
                "game_system": entry.game_system,
                "game_systems": list(entry.game_systems),
            })

    # Files in manifest but no longer selected → to_remove
    to_remove += [
        {
            "path": path_str,
            "filename": manifest.files[path_str].filename,
            "chunk_count": manifest.files[path_str].chunk_count,
            "game_system": manifest.files[path_str].game_system,
            "game_systems": list(manifest.files[path_str].game_systems),
        }
        for path_str in (indexed - selected)
    ]

    # --- Rename detection ---
    # Match to_add files against to_remove files by content hash.
    # Uses file_size as a cheap pre-filter before computing SHA-256.
    to_rename = []
    if to_add and to_remove:
        # Build lookup from content_hash → to_remove entry (only entries with a hash)
        remove_by_hash: dict[str, list[dict]] = {}
        remove_sizes: dict[int, list[str]] = {}
        for entry in to_remove:
            manifest_entry = manifest.files[entry["path"]]
            if manifest_entry.content_hash:
                remove_by_hash.setdefault(manifest_entry.content_hash, []).append(entry)
            if manifest_entry.file_size:
                remove_sizes.setdefault(manifest_entry.file_size, []).append(
                    manifest_entry.content_hash
                )

        if remove_by_hash:
            matched_add = set()
            matched_remove = set()

            for i, add_entry in enumerate(to_add):
                add_path = Path(add_entry["path"])
                add_size = os.path.getsize(add_path)

                # Cheap pre-filter: skip if no removed file has the same size
                candidate_hashes = remove_sizes.get(add_size)
                if not candidate_hashes:
                    continue

                add_hash = file_content_hash(add_path)
                candidates = remove_by_hash.get(add_hash)
                if not candidates:
                    continue

                # Find the first unmatched candidate
                for rm_entry in candidates:
                    if rm_entry["path"] not in matched_remove:
                        matched_add.add(i)
                        matched_remove.add(rm_entry["path"])
                        to_rename.append({
                            "old_path": rm_entry["path"],
                            "new_path": add_entry["path"],
                            "filename": add_entry["filename"],
                            "old_filename": rm_entry["filename"],
                            "chunk_count": rm_entry["chunk_count"],
                            "game_system": rm_entry["game_system"],
                            "game_systems": list(rm_entry.get("game_systems", [])),
                            "content_hash": add_hash,
                        })
                        break

            # Remove matched entries from to_add and to_remove
            if matched_add:
                to_add = [e for i, e in enumerate(to_add) if i not in matched_add]
            if matched_remove:
                to_remove = [e for e in to_remove if e["path"] not in matched_remove]

    return {
        "to_add": to_add,
        "to_remove": to_remove,
        "to_auto_remove": to_auto_remove,
        "to_rename": to_rename,
        "to_update": to_update,
        "up_to_date": up_to_date,
        "errors": errors,
        "stale_paths": stale_paths,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    collection=None,
    data_dir: Path | None = None,
    chroma_client=None,
    embedding_function=None,
):
    """Create the FastAPI app, optionally with a pre-configured collection.

    In production: called with no arguments — sets up Ollama + PersistentClient.
    In tests: called with a test collection (EphemeralClient + ONNX embeddings).

    Tests that need to exercise endpoints that recreate the collection
    (e.g. delete-index, which drops the collection to reset its vector-dim
    binding after an embedding-model change) can pass `chroma_client` and
    `embedding_function` so the recreate path has the dependencies it needs.

    Args:
        collection: ChromaDB collection (None = production auto-setup).
        data_dir: Directory for ChromaDB and manifest storage.
                  In production, resolved from --data-dir CLI arg.
                  In tests, pass tmp_path.
        chroma_client: ChromaDB client owning ``collection``. Required for
                  the delete-index recreate path; ``None`` falls back to
                  row-by-row delete (sufficient when dim never changes).
        embedding_function: Embedding function for collection recreate.
                  Paired with ``chroma_client``.
    """
    if collection is None:
        # Production path: same setup as before, but now only runs
        # when the server is actually started (not at import time).
        args = parse_args()
        data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"
        data_dir.mkdir(parents=True, exist_ok=True)

        chroma_client = chromadb.PersistentClient(path=str(data_dir))
        reclaimed = gc_orphan_segments(data_dir)
        if reclaimed > 0:
            print(f"[gc] removed orphan segment dirs: {reclaimed:,} bytes reclaimed")
        embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name="bge-m3"
        )
        collection = chroma_client.get_or_create_collection(
            name="ttrpg_docs",
            embedding_function=embedding_function,
        )

    app = FastAPI(title="Legend Lore Sidecar")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # MCP connection tracking — heartbeat + activity timestamps. Tracked
    # in-memory; any agent reconnect resends a heartbeat within 30s.
    app.state.mcp_last_heartbeat = None
    app.state.mcp_last_query = None

    # ------------------------------------------------------------------
    # Concurrency guard — prevents two syncs from running simultaneously.
    # The streaming sync uses a synchronous generator, so we use a
    # threading.Lock rather than asyncio.Lock.
    _sync_lock = threading.Lock()

    def acquire_sync_lock_or_409():
        """Acquire the sync lock non-blockingly. 409 if already held.

        Manual form for streaming endpoints, where the lock needs to span
        the SSE generator's iteration (which outlives the handler).
        """
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already in progress"
            )

    @contextmanager
    def sync_lock_or_409():
        """Acquire-or-409, then release on exit. For non-streaming endpoints."""
        acquire_sync_lock_or_409()
        try:
            yield
        finally:
            _sync_lock.release()

    # Merged game systems state — rebuilt when custom systems change.
    # Mutable container so endpoint closures always see the latest value.
    _custom_store = load_custom_systems(data_dir) if data_dir else CustomGameSystemsStore()
    _merged_list, _merged_known = get_merged_systems(_custom_store)
    _merged = {"list": _merged_list, "known": _merged_known}

    def _rebuild_merged():
        """Reload custom systems from disk and rebuild the merged state."""
        store = load_custom_systems(data_dir) if data_dir else CustomGameSystemsStore()
        merged_list, merged_known = get_merged_systems(store)
        _merged["list"] = merged_list
        _merged["known"] = merged_known

    # Endpoints (close over `collection` from the factory)
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health():
        """Health check for startup detection."""
        return {"status": "ok"}

    @app.post("/api/mcp-heartbeat")
    async def mcp_heartbeat():
        """Heartbeat ping from the MCP server (sent every ~30s).

        Used by the desktop UI to render a "MCP connected" indicator.
        Connection is considered live if the last heartbeat is within 60s.
        """
        app.state.mcp_last_heartbeat = datetime.now(timezone.utc)
        return {"ok": True}

    @app.get("/api/mcp-status")
    async def mcp_status():
        """Current MCP connection state, derived from heartbeat + activity."""
        now = datetime.now(timezone.utc)
        hb = app.state.mcp_last_heartbeat
        lq = app.state.mcp_last_query
        connected = bool(hb and (now - hb).total_seconds() <= 60)
        active = bool(lq and (now - lq).total_seconds() <= 5)
        return {
            "connected": connected,
            "active": active,
            "last_heartbeat_at": hb.isoformat() if hb else None,
            "last_query_at": lq.isoformat() if lq else None,
        }

    @app.post("/api/index-files")
    def index_files(request: IndexFilesRequest):
        """Index specific PDF files by path.

        Declared as plain ``def`` (not ``async def``) so FastAPI runs the
        body in a worker thread. Indexing does heavy synchronous work
        (PyMuPDF + Ollama + Chroma); putting it on the event loop would
        block ``/health`` polls and other concurrent requests.
        """
        total = len(request.paths)
        indexed = 0
        errors = []
        manifest = load_manifest(data_dir) if data_dir else None

        for pdf_path_str in request.paths:
            pdf_path = Path(pdf_path_str)
            chunk_count, error, detected_system, detected_systems = index_single_pdf(
                pdf_path, collection, game_system=request.game_system,
                known_systems=_merged["known"], data_dir=data_dir,
            )

            if error:
                errors.append(error)
            else:
                indexed += 1
                if manifest and data_dir:
                    manifest.files[pdf_path_str] = ManifestEntry(
                        filename=pdf_path.name,
                        mtime=os.path.getmtime(pdf_path),
                        chunk_count=chunk_count,
                        indexed_at=datetime.now(timezone.utc).isoformat(),
                        game_system=detected_system,
                        game_systems=detected_systems,
                        content_hash=file_content_hash(pdf_path),
                        file_size=os.path.getsize(pdf_path),
                    )

        if manifest and data_dir:
            save_manifest(data_dir, manifest)

        return {
            "indexed": indexed,
            "total": total,
            "errors": errors
        }

    @app.post("/api/reindex-file")
    def reindex_file(request: ReindexFileRequest):
        """Force re-index a single file: drop existing chunks, then re-add.

        Unlike sync_index, runs even when mtime/hash are unchanged — used by
        the right-click "Re-index file" action when the user wants to rebuild
        chunks regardless of file state (e.g. after a chunker change).

        Declared as plain ``def`` so the heavy synchronous work runs in a
        worker thread and doesn't block the event loop.
        """
        with sync_lock_or_409():
            pdf_path = Path(request.path)
            if not pdf_path.exists():
                raise HTTPException(
                    status_code=404, detail=f"File not found: {request.path}"
                )

            delete_source_chunks(request.path, collection, data_dir)

            chunk_count, error, detected_system, detected_systems = index_single_pdf(
                pdf_path, collection, game_system=request.game_system,
                known_systems=_merged["known"], data_dir=data_dir,
            )

            if error:
                return {"chunks": 0, "game_system": detected_system, "error": error}

            if data_dir:
                manifest = load_manifest(data_dir)
                manifest.files[request.path] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=chunk_count,
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
                    game_systems=detected_systems,
                    content_hash=file_content_hash(pdf_path),
                    file_size=os.path.getsize(pdf_path),
                )
                save_manifest(data_dir, manifest)

            return {
                "chunks": chunk_count,
                "game_system": detected_system,
                "error": None,
            }

    @app.post("/api/index-status")
    async def index_status(request: IndexStatusRequest):
        """Compare selected files against the current index.

        Read-only — does not modify the index or manifest.
        Returns categorized lists: to_add, to_remove, to_update, up_to_date.
        """
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        manifest = load_manifest(data_dir)
        diff = compute_diff(request.selected_paths, manifest)

        return {
            **diff,
            "summary": {
                "add": len(diff["to_add"]),
                "remove": len(diff["to_remove"]),
                "auto_remove": len(diff["to_auto_remove"]),
                "rename": len(diff["to_rename"]),
                "update": len(diff["to_update"]),
                "up_to_date": len(diff["up_to_date"]),
                "errors": len(diff["errors"]),
                "stale": len(diff["stale_paths"]),
            },
        }


    def _sync_core(request: SyncIndexRequest):
        """Core sync generator shared by both endpoints.

        Yields progress dicts with an ``event`` key (``started``, ``progress``,
        or ``complete``).  The ``complete`` event contains the full result.
        """
        manifest = load_manifest(data_dir)
        diff = compute_diff(request.selected_paths, manifest)
        if request.force:
            # Reindex-all: treat unchanged files as needing reprocessing.
            diff["to_update"] = diff["to_update"] + diff["up_to_date"]
            diff["up_to_date"] = []

        total_files = (
            len(diff["to_remove"])
            + len(diff["to_auto_remove"])
            + len(diff["to_rename"])
            + len(diff["to_add"])
            + len(diff["to_update"])
        )
        files_done = 0
        chunks_total = 0
        removed = 0
        auto_removed = 0
        renamed = 0
        added = 0
        updated = 0
        errors = []

        yield {"event": "started", "total_files": total_files}

        # Phase 1: Remove deselected files
        for entry in diff["to_remove"]:
            deleted = delete_source_chunks(entry["path"], collection, data_dir=data_dir)
            del manifest.files[entry["path"]]
            save_manifest(data_dir, manifest)
            removed += 1
            files_done += 1
            chunks_total += deleted
            yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": entry["filename"], "phase": "remove"}

        # Phase 1a: Auto-remove files deleted from disk
        for entry in diff["to_auto_remove"]:
            deleted = delete_source_chunks(entry["path"], collection, data_dir=data_dir)
            del manifest.files[entry["path"]]
            save_manifest(data_dir, manifest)
            auto_removed += 1
            files_done += 1
            chunks_total += deleted
            yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": entry["filename"], "phase": "auto_remove"}

        # Phase 1.5: Handle renames (transfer chunks without re-embedding)
        for entry in diff["to_rename"]:
            old_path_str = entry["old_path"]
            new_path = Path(entry["new_path"])

            results = collection.get(
                where={"source": old_path_str},
                include=["embeddings", "documents", "metadatas"],
            )

            transferred = 0
            if results["ids"]:
                collection.delete(ids=results["ids"])
                prefix = chunk_id_prefix(new_path)
                new_ids = [f"{prefix}_{i}" for i in range(len(results["ids"]))]
                new_metadatas = [
                    {**m, "source": str(new_path), "filename": new_path.name}
                    for m in results["metadatas"]
                ]
                collection.add(
                    ids=new_ids,
                    documents=results["documents"],
                    embeddings=results["embeddings"],
                    metadatas=new_metadatas,
                )
                transferred = len(results["ids"])

            del manifest.files[old_path_str]
            manifest.files[entry["new_path"]] = ManifestEntry(
                filename=new_path.name,
                mtime=os.path.getmtime(new_path),
                chunk_count=entry["chunk_count"],
                indexed_at=datetime.now(timezone.utc).isoformat(),
                game_system=entry["game_system"],
                game_systems=list(entry.get("game_systems", [])),
                content_hash=entry["content_hash"],
                file_size=os.path.getsize(new_path),
            )
            save_manifest(data_dir, manifest)
            renamed += 1
            files_done += 1
            chunks_total += transferred
            yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": new_path.name, "phase": "rename"}

        # Phase 2: Index new files
        for entry in diff["to_add"]:
            pdf_path = Path(entry["path"])
            override = (
                request.game_system_overrides.get(entry["path"])
                if request.game_system_overrides else None
            )
            chunks, detected_system, detected_systems, error = prepare_pdf(
                pdf_path, game_system=override,
                known_systems=_merged["known"],
            )
            if error:
                errors.append(error)
                files_done += 1
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}
            else:
                embed_units, parents = build_granularity(chunks)
                if data_dir:
                    upsert_parents(data_dir, str(pdf_path), parents)
                prefix = chunk_id_prefix(pdf_path)
                for n in _embed_and_upsert_units(
                    collection, embed_units, pdf_path, detected_system, prefix,
                ):
                    chunks_total += n
                    yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}
                added += 1
                files_done += 1
                manifest.files[entry["path"]] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=len(embed_units),
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
                    game_systems=detected_systems,
                    content_hash=file_content_hash(pdf_path),
                    file_size=os.path.getsize(pdf_path),
                )
                save_manifest(data_dir, manifest)
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}

        # Phase 3: Re-index modified files (delete old chunks first to prevent orphans)
        for entry in diff["to_update"]:
            delete_source_chunks(entry["path"], collection, data_dir=data_dir)
            pdf_path = Path(entry["path"])
            override = (
                request.game_system_overrides.get(entry["path"])
                if request.game_system_overrides else None
            )
            chunks, detected_system, detected_systems, error = prepare_pdf(
                pdf_path, game_system=override,
                known_systems=_merged["known"],
            )
            if error:
                errors.append(error)
                files_done += 1
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
            else:
                embed_units, parents = build_granularity(chunks)
                if data_dir:
                    upsert_parents(data_dir, str(pdf_path), parents)
                prefix = chunk_id_prefix(pdf_path)
                for n in _embed_and_upsert_units(
                    collection, embed_units, pdf_path, detected_system, prefix,
                ):
                    chunks_total += n
                    yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
                updated += 1
                files_done += 1
                manifest.files[entry["path"]] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=len(embed_units),
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
                    game_systems=detected_systems,
                    content_hash=file_content_hash(pdf_path),
                    file_size=os.path.getsize(pdf_path),
                )
                save_manifest(data_dir, manifest)
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}

        # Update collections that reference renamed or auto-removed paths
        if renamed > 0 or auto_removed > 0:
            coll_store = load_collections(data_dir)
            coll_changed = False

            if renamed > 0:
                rename_map = {e["old_path"]: e["new_path"] for e in diff["to_rename"]}
                for coll in coll_store.collections.values():
                    updated_paths = [rename_map.get(p, p) for p in coll.file_paths]
                    if updated_paths != coll.file_paths:
                        coll.file_paths = updated_paths
                        coll.updated_at = _now_iso()
                        coll_changed = True

            if auto_removed > 0:
                removed_paths = {e["path"] for e in diff["to_auto_remove"]}
                for coll in coll_store.collections.values():
                    filtered = [p for p in coll.file_paths if p not in removed_paths]
                    if len(filtered) != len(coll.file_paths):
                        coll.file_paths = filtered
                        coll.updated_at = _now_iso()
                        coll_changed = True

            if coll_changed:
                save_collections(data_dir, coll_store)

        yield {
            "event": "complete",
            "added": added,
            "removed": removed,
            "auto_removed": auto_removed,
            "renamed": renamed,
            "updated": updated,
            "errors": errors,
            "total_indexed": len(manifest.files),
            "chunks_total": chunks_total,
            "renames": [
                {"old_path": e["old_path"], "new_path": e["new_path"]}
                for e in diff["to_rename"]
            ],
            "auto_removed_paths": [e["path"] for e in diff["to_auto_remove"]],
            "stale_paths": diff["stale_paths"],
        }

    def _do_sync(request: SyncIndexRequest):
        """Run sync and return the final result dict.

        Synchronous helper used by ``/api/sync-index`` (test convenience
        endpoint). Production callers use the streaming variant below.
        """
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )
        result = None
        for event in _sync_core(request):
            if event["event"] == "complete":
                result = event
        if result:
            del result["event"]
        return result

    @app.post("/api/sync-index")
    async def sync_index(request: SyncIndexRequest):
        """Apply index changes synchronously (test convenience endpoint).

        Production code uses ``/api/sync-index-stream`` for SSE progress.
        """
        with sync_lock_or_409():
            return _do_sync(request)

    @app.post("/api/sync-index-stream")
    async def sync_index_stream(request: SyncIndexRequest):
        """Streaming version of sync-index that emits SSE progress events."""
        acquire_sync_lock_or_409()
        if not data_dir:
            _sync_lock.release()
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        def generate_with_lock():
            try:
                for event in _sync_core(request):
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                _sync_lock.release()

        return StreamingResponse(generate_with_lock(), media_type="text/event-stream")

    @app.post("/api/reindex-all-stream")
    async def reindex_all_stream():
        """Force re-extraction and re-embedding of every indexed file.

        Streams the same SSE progress events as ``/api/sync-index-stream``.
        Reuses the sync pipeline with ``force=True`` over all currently
        indexed paths, so unchanged-on-disk files are re-processed with the
        current extractor.
        """
        acquire_sync_lock_or_409()
        if not data_dir:
            _sync_lock.release()
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        manifest = load_manifest(data_dir)
        request = SyncIndexRequest(
            selected_paths=list(manifest.files.keys()),
            force=True,
        )

        def generate_with_lock():
            try:
                for event in _sync_core(request):
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                _sync_lock.release()

        return StreamingResponse(generate_with_lock(), media_type="text/event-stream")

    @app.post("/api/delete-index")
    async def delete_index():
        """Purge every chunk from ChromaDB and clear the manifest.

        Drops and recreates the underlying Chroma collection rather than
        only deleting rows. Chroma locks a collection's vector dim to the
        first inserted embedding; deleting rows preserves that lock, so
        an embedding-model change (e.g. nomic 768 → bge-m3 1024) leaves
        the collection unable to accept new vectors. Recreating resets
        the dim binding so the next re-index works against the current
        embedding function.

        Preserves the selected folder, game systems, and user-curated
        collections in full (collections store file paths, not chunk
        IDs — those paths are still valid on disk and will resolve
        again after the next sync re-creates their chunks).
        """
        nonlocal collection
        with sync_lock_or_409():
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )

            manifest = load_manifest(data_dir)
            removed_files = len(manifest.files)

            removed_chunks = len(collection.get(include=[])["ids"])

            if chroma_client is not None:
                collection_name = collection.name
                # Capture segment dir UUIDs before delete_collection wipes them
                # from sqlite — Chroma only removes metadata rows, not the
                # on-disk dirs, so we have to rmtree them ourselves.
                old_segment_ids = (
                    _segment_ids_for_collection(data_dir, collection_name)
                    if data_dir else []
                )
                chroma_client.delete_collection(name=collection_name)
                collection = chroma_client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=embedding_function,
                )
                if data_dir:
                    for sid in old_segment_ids:
                        _remove_segment_dir(data_dir, sid)
            elif removed_chunks:
                # Test path without an injected chroma_client — the dim is
                # fixed by the fixture and never changes, so row-delete is
                # sufficient.
                collection.delete(ids=collection.get(include=[])["ids"])

            clear_all_parents(data_dir)
            save_manifest(data_dir, IndexManifest())

            return {"removed_files": removed_files, "removed_chunks": removed_chunks}

    # ------------------------------------------------------------------
    # File rename — direct index update (no re-embedding)
    # ------------------------------------------------------------------

    class FileRenameRequest(BaseModel):
        old_path: str
        new_path: str

    @app.post("/api/file-rename")
    async def file_rename(request: FileRenameRequest):
        """Rename a single file's index entry without re-embedding.

        Transfers ChromaDB chunks to the new path, updates the manifest
        and collections.
        """
        with sync_lock_or_409():
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )

            manifest = load_manifest(data_dir)
            old_path_str = request.old_path
            new_path_str = request.new_path
            new_path = Path(new_path_str)

            if old_path_str not in manifest.files:
                return {"renamed": False, "reason": "not_indexed"}

            # Transfer chunks: get → delete → re-add with new IDs/metadata
            results = collection.get(
                where={"source": old_path_str},
                include=["embeddings", "documents", "metadatas"],
            )
            if results["ids"]:
                collection.delete(ids=results["ids"])
                prefix = chunk_id_prefix(new_path)
                new_ids = [f"{prefix}_{i}" for i in range(len(results["ids"]))]
                new_metadatas = [
                    {**m, "source": new_path_str, "filename": new_path.name}
                    for m in results["metadatas"]
                ]
                collection.add(
                    ids=new_ids,
                    documents=results["documents"],
                    embeddings=results["embeddings"],
                    metadatas=new_metadatas,
                )

            # Update manifest
            old_entry = manifest.files.pop(old_path_str)
            manifest.files[new_path_str] = ManifestEntry(
                filename=new_path.name,
                mtime=old_entry.mtime,
                chunk_count=old_entry.chunk_count,
                indexed_at=datetime.now(timezone.utc).isoformat(),
                game_system=old_entry.game_system,
                game_systems=list(old_entry.game_systems),
                content_hash=old_entry.content_hash,
                file_size=old_entry.file_size,
            )
            save_manifest(data_dir, manifest)

            # Update collections
            affected_collections = 0
            coll_store = load_collections(data_dir)
            for coll in coll_store.collections.values():
                if old_path_str in coll.file_paths:
                    coll.file_paths = [
                        new_path_str if p == old_path_str else p
                        for p in coll.file_paths
                    ]
                    coll.updated_at = _now_iso()
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {"renamed": True, "affected_collections": affected_collections}

    class FileDeleteRequest(BaseModel):
        path: str

    @app.post("/api/file-delete")
    async def file_delete(request: FileDeleteRequest):
        """Remove a single file's index entry immediately.

        Deletes chunks from ChromaDB and cleans up the manifest and
        collections.
        """
        with sync_lock_or_409():
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )

            manifest = load_manifest(data_dir)
            path_str = request.path

            if path_str not in manifest.files:
                return {"deleted": False, "reason": "not_indexed"}

            delete_source_chunks(path_str, collection, data_dir=data_dir)
            del manifest.files[path_str]
            save_manifest(data_dir, manifest)

            # Update collections
            affected_collections = 0
            coll_store = load_collections(data_dir)
            for coll in coll_store.collections.values():
                if path_str in coll.file_paths:
                    coll.file_paths = [p for p in coll.file_paths if p != path_str]
                    coll.updated_at = _now_iso()
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {"deleted": True, "affected_collections": affected_collections}

    # ------------------------------------------------------------------
    # Folder operations — batch rename / delete for all children
    # ------------------------------------------------------------------

    class FolderRenameRequest(BaseModel):
        old_prefix: str
        new_prefix: str

    class FolderDeleteRequest(BaseModel):
        folder_prefix: str

    @app.post("/api/folder-rename")
    async def folder_rename(request: FolderRenameRequest):
        """Batch-rename all indexed files under a folder prefix.

        Transfers ChromaDB chunks without re-embedding, updates the
        manifest and collections.
        """
        with sync_lock_or_409():
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )

            manifest = load_manifest(data_dir)
            old_prefix = request.old_prefix.rstrip("/")
            new_prefix = request.new_prefix.rstrip("/")
            child_prefix = old_prefix + "/"

            matched_paths = [
                p for p in manifest.files
                if p.startswith(child_prefix)
            ]

            renamed_files = 0
            for old_path_str in matched_paths:
                new_path_str = new_prefix + old_path_str[len(old_prefix):]
                new_path = Path(new_path_str)

                # Transfer chunks: get → delete → re-add with new IDs/metadata
                results = collection.get(
                    where={"source": old_path_str},
                    include=["embeddings", "documents", "metadatas"],
                )
                if results["ids"]:
                    collection.delete(ids=results["ids"])
                    prefix = chunk_id_prefix(new_path)
                    new_ids = [f"{prefix}_{i}" for i in range(len(results["ids"]))]
                    new_metadatas = [
                        {**m, "source": new_path_str, "filename": new_path.name}
                        for m in results["metadatas"]
                    ]
                    collection.add(
                        ids=new_ids,
                        documents=results["documents"],
                        embeddings=results["embeddings"],
                        metadatas=new_metadatas,
                    )

                # Update manifest
                old_entry = manifest.files.pop(old_path_str)
                manifest.files[new_path_str] = ManifestEntry(
                    filename=new_path.name,
                    mtime=old_entry.mtime,
                    chunk_count=old_entry.chunk_count,
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=old_entry.game_system,
                    game_systems=list(old_entry.game_systems),
                    content_hash=old_entry.content_hash,
                    file_size=old_entry.file_size,
                )
                renamed_files += 1

            save_manifest(data_dir, manifest)

            # Update collections
            affected_collections = 0
            coll_store = load_collections(data_dir)
            for coll in coll_store.collections.values():
                updated_paths = [
                    new_prefix + p[len(old_prefix):] if p.startswith(child_prefix) else p
                    for p in coll.file_paths
                ]
                if updated_paths != coll.file_paths:
                    coll.file_paths = updated_paths
                    coll.updated_at = _now_iso()
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {
                "renamed_files": renamed_files,
                "affected_collections": affected_collections,
            }

    @app.post("/api/folder-delete")
    async def folder_delete(request: FolderDeleteRequest):
        """Batch-delete all indexed files under a folder prefix.

        Removes chunks from ChromaDB and cleans up the manifest and
        collections.
        """
        with sync_lock_or_409():
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )

            manifest = load_manifest(data_dir)
            folder_prefix = request.folder_prefix.rstrip("/")
            child_prefix = folder_prefix + "/"

            matched_paths = [
                p for p in manifest.files
                if p.startswith(child_prefix)
            ]

            deleted_files = 0
            for path_str in matched_paths:
                delete_source_chunks(path_str, collection, data_dir=data_dir)
                del manifest.files[path_str]
                deleted_files += 1

            save_manifest(data_dir, manifest)

            # Update collections
            affected_collections = 0
            coll_store = load_collections(data_dir)
            for coll in coll_store.collections.values():
                filtered = [p for p in coll.file_paths if not p.startswith(child_prefix)]
                if len(filtered) != len(coll.file_paths):
                    coll.file_paths = filtered
                    coll.updated_at = _now_iso()
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {
                "deleted_files": deleted_files,
                "affected_collections": affected_collections,
            }

    @app.get("/api/stats")
    async def get_stats():
        """Database statistics."""
        try:
            count = collection.count()
            results = collection.get(include=["metadatas"])
            unique_sources = (
                len(set(m.get("filename") for m in results["metadatas"]))
                if results["metadatas"] else 0
            )
            storage_bytes = 0
            if data_dir and data_dir.exists():
                for dirpath, _dirnames, filenames in os.walk(data_dir):
                    for f in filenames:
                        storage_bytes += os.path.getsize(os.path.join(dirpath, f))

            # Calculate reclaimable space: SQLite freelist pages across both
            # stores + bytes locked up in orphan segment dirs. Mirrors what
            # `/api/compact` actually reclaims, so the UI's "Compact" button
            # only appears when there's something to recover.
            reclaimable_bytes = _compute_reclaimable_bytes(data_dir)

            return {
                "total_chunks": count,
                "total_documents": unique_sources,
                "collection_name": collection.name,
                "storage_bytes": storage_bytes,
                "reclaimable_bytes": reclaimable_bytes,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/compact")
    async def compact_database():
        """Compact the ChromaDB database to reclaim disk space.

        VACUUMs ``chroma.sqlite3`` and removes any orphan segment dirs left
        behind by previous ``delete_collection`` calls (Chroma's behavior:
        metadata rows are removed but on-disk dirs are not).
        """
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        sqlite_path = data_dir / "chroma.sqlite3"
        if not sqlite_path.exists():
            raise HTTPException(
                status_code=404, detail="Database file not found"
            )

        size_before = os.path.getsize(sqlite_path)
        sqlite_reclaimed = compact_sqlite(data_dir)
        orphan_reclaimed = gc_orphan_segments(data_dir)

        return {
            "size_before": size_before,
            "size_after": os.path.getsize(sqlite_path),
            "reclaimed": sqlite_reclaimed + orphan_reclaimed,
        }

    @app.get("/api/sources")
    async def get_sources():
        """List all indexed PDFs with per-source stats."""
        try:
            results = collection.get(include=["metadatas"])
            if not results["metadatas"]:
                return {"sources": [], "count": 0}

            manifest = load_manifest(data_dir) if data_dir else IndexManifest()

            sources_info = {}
            for metadata in results["metadatas"]:
                filename = metadata["filename"]
                if filename not in sources_info:
                    source_path = metadata.get("source", "")
                    entry = manifest.files.get(source_path)
                    primary = metadata.get("game_system", "unknown")
                    if entry and entry.game_systems:
                        systems = list(entry.game_systems)
                    elif primary != "unknown":
                        systems = [primary]
                    else:
                        systems = []
                    sources_info[filename] = {
                        "filename": filename,
                        "source": source_path,
                        "chunks": 0,
                        "game_system": primary,
                        "game_systems": systems,
                        "pages": 0,
                        "indexed_at": entry.indexed_at if entry else None,
                        "file_size_bytes": entry.file_size if entry else None,
                    }
                sources_info[filename]["chunks"] += 1
                page_end = metadata.get("page_end")
                if isinstance(page_end, int) and page_end > sources_info[filename]["pages"]:
                    sources_info[filename]["pages"] = page_end

            sources_list = sorted(sources_info.values(), key=lambda x: x["filename"])
            return {"sources": sources_list, "count": len(sources_list)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/game-systems")
    async def get_game_systems():
        """List all distinct game systems found in the index."""
        try:
            results = collection.get(include=["metadatas"])
            if not results["metadatas"]:
                return {"game_systems": [], "count": 0}

            systems = set()
            for metadata in results["metadatas"]:
                systems.add(metadata.get("game_system", "unknown"))

            sorted_systems = sorted(systems)
            return {"game_systems": sorted_systems, "count": len(sorted_systems)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/known-game-systems")
    async def get_known_game_systems():
        """Return all active game systems (built-in + custom, minus disabled)."""
        systems = sorted(
            [
                {
                    "tag": e["tag"],
                    "keywords": e.get("keywords", []),
                    "color": e.get("color"),
                    "is_builtin": e.get("is_builtin", True),
                    "is_customized": e.get("is_customized", False),
                }
                for e in _merged["list"]
            ],
            key=lambda s: s["tag"].lower(),
        )
        return {"systems": systems}

    def _apply_game_systems(filename: str, game_systems: list[str]) -> dict:
        """Update Chroma chunk metadata + manifest entry for a file's tags.

        ``game_systems[0]`` becomes the primary scalar in chunk metadata
        (and the manifest's ``game_system`` field). The full list is
        written to the manifest's ``game_systems`` field. An empty list
        clears both back to ``"unknown"`` / ``[]``.
        """
        primary = game_systems[0] if game_systems else "unknown"

        manifest = load_manifest(data_dir) if data_dir else None
        source_path = None
        if manifest:
            for path_str, entry in manifest.files.items():
                if entry.filename == filename:
                    source_path = path_str
                    break

        if not source_path:
            raise HTTPException(
                status_code=404,
                detail=f"Source not found: {filename}",
            )

        results = collection.get(
            where={"source": source_path},
            include=["metadatas"],
        )

        if not results["ids"]:
            raise HTTPException(
                status_code=404,
                detail=f"Source not found: {filename}",
            )

        updated_metadatas = [
            {**metadata, "game_system": primary}
            for metadata in results["metadatas"]
        ]

        collection.update(
            ids=results["ids"],
            metadatas=updated_metadatas,
        )

        if manifest:
            for entry in manifest.files.values():
                if entry.filename == filename:
                    entry.game_system = primary
                    entry.game_systems = list(game_systems)
            save_manifest(data_dir, manifest)

        return {
            "filename": filename,
            "game_system": primary,
            "game_systems": list(game_systems),
            "chunks_updated": len(results["ids"]),
        }

    @app.post("/api/set-game-system")
    async def set_game_system(request: SetGameSystemRequest):
        """Update the game system tag for all chunks of a file.

        Changes metadata in ChromaDB and the manifest without re-indexing.
        Back-compat alias for the multi-tag endpoint.
        """
        try:
            return _apply_game_systems(request.filename, [request.game_system])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/set-game-systems")
    async def set_game_systems(request: SetGameSystemsRequest):
        """Update multiple game system tags for all chunks of a file.

        The first tag becomes the primary stored in ChromaDB metadata; the
        full list is persisted to the manifest. An empty list clears all
        tags back to ``"unknown"``.
        """
        try:
            return _apply_game_systems(request.filename, request.game_systems)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------------------------------
    # Custom game system CRUD
    # ------------------------------------------------------------------

    @app.post("/api/custom-game-systems")
    async def create_custom_game_system(request: CustomGameSystemRequest):
        """Add a new custom game system (or override a built-in)."""
        if not request.tag.strip():
            raise HTTPException(status_code=400, detail="Tag must not be empty")

        store = load_custom_systems(data_dir) if data_dir else CustomGameSystemsStore()

        # Check for duplicate tag among existing custom systems
        custom_tags = {e.tag for e in store.systems}
        if request.tag in custom_tags:
            raise HTTPException(
                status_code=409,
                detail=f"A custom game system with tag '{request.tag}' already exists",
            )

        store.systems.append(CustomGameSystemEntry(
            tag=request.tag,
            keywords=request.keywords,
            color=request.color,
        ))
        if data_dir:
            save_custom_systems(data_dir, store)
        _rebuild_merged()

        return {
            "tag": request.tag,
            "keywords": request.keywords,
            "color": request.color,
        }

    @app.put("/api/custom-game-systems/{tag}")
    async def update_custom_game_system(tag: str, request: CustomGameSystemRequest):
        """Update a custom game system, or create an override for a built-in."""
        store = load_custom_systems(data_dir) if data_dir else CustomGameSystemsStore()

        # Try to update an existing custom entry
        found = False
        for entry in store.systems:
            if entry.tag == tag:
                entry.tag = request.tag
                entry.keywords = request.keywords
                entry.color = request.color
                found = True
                break

        if not found:
            # If it's a built-in, create a custom override
            builtin_tags = {e["tag"] for e in GAME_SYSTEMS}
            if tag in builtin_tags:
                store.systems.append(CustomGameSystemEntry(
                    tag=request.tag,
                    keywords=request.keywords,
                    color=request.color,
                ))
            else:
                raise HTTPException(
                    status_code=404, detail=f"Game system not found: {tag}"
                )

        if data_dir:
            save_custom_systems(data_dir, store)
        _rebuild_merged()

        return {
            "tag": request.tag,
            "keywords": request.keywords,
            "color": request.color,
        }

    @app.delete("/api/custom-game-systems/{tag}")
    async def delete_custom_game_system(tag: str):
        """Remove a custom game system or reset a built-in override."""
        store = load_custom_systems(data_dir) if data_dir else CustomGameSystemsStore()
        original_count = len(store.systems)
        store.systems = [e for e in store.systems if e.tag != tag]

        if len(store.systems) == original_count:
            raise HTTPException(
                status_code=404, detail=f"Custom system not found: {tag}"
            )

        if data_dir:
            save_custom_systems(data_dir, store)
        _rebuild_merged()

        return {"deleted": tag}

    @app.post("/api/custom-game-systems/toggle-builtin")
    async def toggle_builtin_game_system(request: ToggleBuiltinRequest):
        """Enable or disable a built-in game system."""
        builtin_tags = {e["tag"] for e in GAME_SYSTEMS}
        if request.tag not in builtin_tags:
            raise HTTPException(
                status_code=400,
                detail=f"'{request.tag}' is not a built-in game system",
            )

        store = load_custom_systems(data_dir) if data_dir else CustomGameSystemsStore()
        if request.disabled:
            if request.tag not in store.disabled_builtins:
                store.disabled_builtins.append(request.tag)
        else:
            store.disabled_builtins = [
                t for t in store.disabled_builtins if t != request.tag
            ]

        if data_dir:
            save_custom_systems(data_dir, store)
        _rebuild_merged()

        return {"tag": request.tag, "disabled": request.disabled}

    @app.delete("/api/source/{filename}")
    async def delete_source(filename: str):
        """Delete a source and all its chunks."""
        try:
            # Look up the full path from the manifest so we can filter by source
            manifest = load_manifest(data_dir)
            source_path = None
            for path_str, entry in manifest.files.items():
                if entry.filename == filename:
                    source_path = path_str
                    break

            if not source_path:
                raise HTTPException(status_code=404, detail=f"Source not found: {filename}")

            deleted = delete_source_chunks(source_path, collection, data_dir=data_dir)

            if not deleted:
                raise HTTPException(status_code=404, detail=f"Source not found: {filename}")

            compact_sqlite(data_dir)

            return {"message": f"Deleted {deleted} chunks from {filename}"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/source/{filename}/content")
    async def get_source_content(filename: str):
        """Retrieve the full text content of an indexed PDF.

        Fetches all chunks for the given filename from ChromaDB,
        sorts them by chunk index, and concatenates them into
        one continuous text.
        """
        try:
            results = collection.get(
                where={"filename": filename},
                include=["documents", "metadatas"],
            )

            if not results["ids"]:
                raise HTTPException(
                    status_code=404, detail=f"Source not found: {filename}"
                )

            # Sort chunks by their index so the text reads in order
            paired = sorted(
                zip(results["documents"], results["metadatas"]),
                key=lambda pair: pair[1].get("chunk", 0),
            )
            content = "\n".join(doc for doc, _ in paired)

            return {
                "filename": filename,
                "chunks": len(paired),
                "content": content,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------------------------------
    # Collections endpoints
    # ------------------------------------------------------------------

    @app.get("/api/collections")
    async def list_collections():
        """List all document collections."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        return {
            "collections": {
                name: {
                    "id": c.id,
                    "name": c.name,
                    "file_paths": c.file_paths,
                    "file_count": len(c.file_paths),
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "last_used_at": c.last_used_at,
                    "description": c.description,
                    "color": c.color,
                    "archived": c.archived,
                }
                for name, c in store.collections.items()
            },
            "count": len(store.collections),
            "active_context": store.active_context,
        }

    @app.post("/api/collections")
    async def create_collection(request: CreateCollectionRequest):
        """Create a named collection of indexed files."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        if request.name in store.collections:
            raise HTTPException(
                status_code=409,
                detail=f"Collection already exists: {request.name}",
            )
        now = _now_iso()
        store.collections[request.name] = Collection(
            id=str(uuid.uuid4()),
            name=request.name,
            file_paths=request.file_paths,
            created_at=now,
            updated_at=now,
            description=request.description,
            color=request.color,
        )
        save_collections(data_dir, store)
        return {"name": request.name, "file_count": len(request.file_paths)}

    @app.put("/api/collections/{name}")
    async def update_collection(name: str, request: UpdateCollectionRequest):
        """Update a collection. All fields optional — only provided fields change."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        if name not in store.collections:
            raise HTTPException(
                status_code=404, detail=f"Collection not found: {name}"
            )
        coll = store.collections[name]
        changed = False
        if request.file_paths is not None:
            coll.file_paths = request.file_paths
            changed = True
        if request.description is not None:
            coll.description = request.description
            changed = True
        if request.color is not None:
            coll.color = request.color
            changed = True
        if request.archived is not None:
            coll.archived = request.archived
            changed = True
        if request.last_used_at is not None:
            coll.last_used_at = request.last_used_at
            changed = True
        if changed:
            coll.updated_at = _now_iso()
        save_collections(data_dir, store)
        return {"name": name, "file_count": len(coll.file_paths)}

    @app.delete("/api/collections/{name}")
    async def delete_collection(name: str):
        """Delete a collection. Clears the active context if it points here."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        if name not in store.collections:
            raise HTTPException(
                status_code=404, detail=f"Collection not found: {name}"
            )
        del store.collections[name]
        if store.active_context == name:
            store.active_context = None
        save_collections(data_dir, store)
        return {"message": f"Deleted collection: {name}"}

    # ------------------------------------------------------------------
    # Active context — currently-scoped collection for tree filter + MCP
    # ------------------------------------------------------------------

    @app.get("/api/active-context")
    async def get_active_context():
        """Return the name of the currently active collection, or null."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        return {"active_context": store.active_context}

    @app.post("/api/active-context")
    async def set_active_context(request: SetActiveContextRequest):
        """Set the active context to a collection. Touches last_used_at."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        if request.name not in store.collections:
            raise HTTPException(
                status_code=404, detail=f"Collection not found: {request.name}"
            )
        store.active_context = request.name
        now = _now_iso()
        coll = store.collections[request.name]
        coll.last_used_at = now
        coll.updated_at = now
        save_collections(data_dir, store)
        return {"active_context": store.active_context}

    @app.delete("/api/active-context")
    async def clear_active_context():
        """Clear the active context."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        store.active_context = None
        save_collections(data_dir, store)
        return {"active_context": None}

    @app.post("/api/search")
    async def search(request: SearchRequest, http_req: Request):
        """Parent-document semantic search.

        Over-fetches small embed units, dedupes by parent_id (keeping the
        highest-similarity hit per parent), then returns the corresponding
        parent text from the SQLite parents store. Per chunk_granularity_spike,
        dedupe-by-parent is a load-bearing part of the retrieval semantics —
        without it the user sees the same section repeated multiple times.
        """
        if http_req.headers.get("X-Source") == "mcp":
            app.state.mcp_last_query = datetime.now(timezone.utc)
        try:
            # Over-fetch by 10x so dedupe-by-parent still yields top-K parents.
            query_kwargs = {
                "query_texts": [request.query],
                "n_results": request.n_results * 10,
            }

            where_clauses = []
            effective_collection = request.collection
            auto_scoped = False

            # An explicit path scope (file/folder right-click) overrides the
            # collection auto-scope so the user gets exactly what they asked for.
            path_scoped = bool(request.source_paths)

            # Fall back to active context if the caller didn't pick one
            # and didn't ask to bypass it.
            if (
                effective_collection is None
                and not request.search_all
                and not path_scoped
                and data_dir
            ):
                store_peek = load_collections(data_dir)
                if store_peek.active_context in store_peek.collections:
                    effective_collection = store_peek.active_context
                    auto_scoped = True

            if effective_collection:
                if not data_dir:
                    raise HTTPException(
                        status_code=500, detail="No data directory configured"
                    )
                store = load_collections(data_dir)
                if effective_collection not in store.collections:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Collection not found: {effective_collection}",
                    )
                manifest = load_manifest(data_dir)
                filenames = resolve_collection_filenames(
                    store.collections[effective_collection], manifest
                )
                if not filenames:
                    return {
                        "results": [],
                        "message": "Collection has no indexed files.",
                        "effective_collection": effective_collection,
                        "auto_scoped": auto_scoped,
                    }
                where_clauses.append({"filename": {"$in": filenames}})
            if request.source_paths:
                where_clauses.append({"source": {"$in": request.source_paths}})
            if request.source_filter:
                where_clauses.append({"filename": request.source_filter})
            if request.game_system or request.game_systems:
                requested = set(request.game_systems or [])
                if request.game_system:
                    requested.add(request.game_system)

                # Resolve secondary-tag matches via the manifest: any file
                # whose `game_systems` includes a requested tag but whose
                # primary `game_system` (the one stored in chunk metadata)
                # does not. Chroma metadata is scalar-only, so secondary
                # matches must be folded in as a filename `$in` clause.
                secondary_filenames: list[str] = []
                if data_dir:
                    search_manifest = load_manifest(data_dir)
                    for entry in search_manifest.files.values():
                        if entry.game_system in requested:
                            continue
                        if any(t in requested for t in entry.game_systems):
                            secondary_filenames.append(entry.filename)

                if request.game_system:
                    primary_clause: dict = {"game_system": request.game_system}
                else:
                    primary_clause = {"game_system": {"$in": list(requested)}}

                if secondary_filenames:
                    where_clauses.append({
                        "$or": [
                            primary_clause,
                            {"filename": {"$in": secondary_filenames}},
                        ]
                    })
                else:
                    where_clauses.append(primary_clause)

            if len(where_clauses) == 1:
                query_kwargs["where"] = where_clauses[0]
            elif len(where_clauses) > 1:
                query_kwargs["where"] = {"$and": where_clauses}

            results = collection.query(**query_kwargs)

            if not results["documents"][0]:
                return {
                    "results": [],
                    "message": "No results found.",
                    "effective_collection": effective_collection,
                    "auto_scoped": auto_scoped,
                }

            # Dedupe by parent_id, keeping the first hit per parent (Chroma
            # returns results in similarity order, so first = highest).
            seen: set[str] = set()
            picked: list[tuple[dict, float]] = []   # (metadata, distance)
            for metadata, distance in zip(
                results["metadatas"][0],
                results["distances"][0],
            ):
                pid = metadata.get("parent_id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                picked.append((metadata, distance))
                if len(picked) >= request.n_results:
                    break

            parent_docs = fetch_parents(data_dir, [m["parent_id"] for m, _ in picked]) if data_dir else {}

            formatted = []
            for metadata, distance in picked:
                pid = metadata["parent_id"]
                parent = parent_docs.get(pid)
                # Fall back to the embed unit text if the parent row is
                # missing (shouldn't happen post-reindex; defensive).
                text = parent.text if parent else next(
                    (d for d, m in zip(results["documents"][0], results["metadatas"][0])
                     if m.get("parent_id") == pid),
                    "",
                )
                formatted.append({
                    "text": text,
                    "filename": metadata["filename"],
                    "source": metadata.get("source", ""),
                    "section_heading": metadata.get("section_heading", "") or (parent.section_heading if parent else ""),
                    "page_start": parent.page_start if parent else metadata.get("page_start", 0),
                    "page_end": parent.page_end if parent else metadata.get("page_end", 0),
                    "game_system": metadata.get("game_system", "unknown"),
                    "relevance": round(1 - distance, 3),
                })

            return {
                "results": formatted,
                "effective_collection": effective_collection,
                "auto_scoped": auto_scoped,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ---------------------------------------------------------------------------
# Parent-death watchdog
# ---------------------------------------------------------------------------

def _watch_parent(parent_pid: int, poll_interval: float = 2.0) -> None:
    """Background thread: self-terminate when parent process dies.

    On Unix, when a parent process dies, os.getppid() changes (typically
    to 1/launchd). We detect this and send ourselves SIGTERM so uvicorn
    can shut down gracefully.
    """
    while True:
        time.sleep(poll_interval)
        if os.getppid() != parent_pid:
            print(f"Parent process (PID {parent_pid}) died, shutting down sidecar.")
            os.kill(os.getpid(), signal.SIGTERM)
            break


# ---------------------------------------------------------------------------
# Main (only runs when executed directly, NOT when imported by tests)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"
    print(f"Starting sidecar on port {args.port}, data dir: {data_dir}")

    # Start parent-death watchdog (daemon thread — won't block exit)
    parent_pid = os.getppid()
    watchdog = threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True)
    watchdog.start()

    application = create_app()
    uvicorn.run(application, host="127.0.0.1", port=args.port, log_level="info")

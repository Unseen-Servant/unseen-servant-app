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
import random
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn


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


def detect_game_system(
    pdf_path: Path,
    text: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> str:
    """Detect the TTRPG game system from folder path or PDF content.

    Detection priority:
    1. Folder name match (user's deliberate organization)
    2. Content keyword match (first 2000 chars of extracted text)
    3. Fallback to "unknown"

    Args:
        known_systems: Optional tag→keywords dict. When None, uses the
            module-level KNOWN_SYSTEMS (built-in only). Pass a merged dict
            to include user-defined custom systems in detection.
    """
    systems = known_systems if known_systems is not None else KNOWN_SYSTEMS

    # Check path components (folder names)
    path_lower = str(pdf_path).lower()
    for system, keywords in systems.items():
        for keyword in keywords:
            if keyword in path_lower:
                return system

    # Check content if provided
    if text:
        text_sample = text[:2000].lower()
        for system, keywords in systems.items():
            for keyword in keywords:
                if keyword in text_sample:
                    return system

    return "unknown"


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks.

    Why overlapping? If a sentence spans two chunks, the overlap ensures
    it appears fully in at least one chunk, improving search quality.
    """
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


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

class IndexStatusRequest(BaseModel):
    selected_paths: list[str]

class SyncIndexRequest(BaseModel):
    selected_paths: list[str]
    game_system_overrides: dict[str, str] | None = None

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    source_filter: str | None = None
    game_system: str | None = None
    collection: str | None = None

class SetGameSystemRequest(BaseModel):
    filename: str
    game_system: str

class CustomGameSystemRequest(BaseModel):
    tag: str
    keywords: list[str] = []

class ToggleBuiltinRequest(BaseModel):
    tag: str
    disabled: bool

class CreateCollectionRequest(BaseModel):
    name: str
    file_paths: list[str]
    description: str = ""

class UpdateCollectionRequest(BaseModel):
    file_paths: list[str]
    description: str | None = None


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
    content_hash: str = ""
    file_size: int = 0


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


class Collection(BaseModel):
    name: str
    file_paths: list[str]
    created_at: str
    description: str = ""


class CollectionsStore(BaseModel):
    version: int = 1
    collections: dict[str, Collection] = {}


def load_collections(data_dir: Path) -> CollectionsStore:
    """Load collections from disk, or return an empty store."""
    path = data_dir / COLLECTIONS_FILENAME
    if path.exists():
        raw = json.loads(path.read_text())
        return CollectionsStore(**raw)
    return CollectionsStore()


def save_collections(data_dir: Path, store: CollectionsStore) -> None:
    """Write collections to disk atomically."""
    path = data_dir / COLLECTIONS_FILENAME
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(store.model_dump_json(indent=2))
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Custom game systems — user-defined systems that merge with built-ins
# ---------------------------------------------------------------------------

CUSTOM_SYSTEMS_FILENAME = "custom_game_systems.json"


class CustomGameSystemEntry(BaseModel):
    tag: str
    keywords: list[str] = []


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


def get_merged_systems(
    custom_store: CustomGameSystemsStore,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Merge built-in GAME_SYSTEMS with custom overrides/additions.

    Returns (merged_list, known_systems_dict) where:
    - merged_list: full entries with tag, keywords, is_builtin, is_customized
    - known_systems_dict: tag → keywords mapping for detect_game_system
    """
    builtin_tags = {entry["tag"] for entry in GAME_SYSTEMS}
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
        is_override = entry.tag in builtin_tags
        merged.append({
            "tag": entry.tag,
            "keywords": entry.keywords,
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

def index_single_pdf(
    pdf_path: Path, collection, game_system: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> tuple[int, str | None, str]:
    """Extract, chunk, and upsert a single PDF into ChromaDB.

    Returns (chunk_count, error_message, game_system).
    error_message is None on success.
    """
    if not pdf_path.exists():
        return 0, f"{pdf_path.name}: File not found", "unknown"

    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        if not text.strip():
            return 0, f"{pdf_path.name}: Empty or scanned PDF", "unknown"

        resolved_system = game_system or detect_game_system(
            pdf_path, text, known_systems=known_systems
        )
        chunks = chunk_text(text)

        batch_size = 100
        for batch_idx in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_idx:batch_idx + batch_size]
            batch_metadatas = [{
                "source": str(pdf_path),
                "filename": pdf_path.name,
                "chunk": batch_idx + chunk_idx,
                "game_system": resolved_system,
            } for chunk_idx in range(len(batch_chunks))]
            prefix = chunk_id_prefix(pdf_path)
            batch_ids = [
                f"{prefix}_{batch_idx + chunk_idx}"
                for chunk_idx in range(len(batch_chunks))
            ]

            collection.upsert(
                documents=batch_chunks,
                metadatas=batch_metadatas,
                ids=batch_ids
            )

        return len(chunks), None, resolved_system

    except Exception as e:
        return 0, f"{pdf_path.name}: {str(e)}", "unknown"


def prepare_pdf(
    pdf_path: Path, game_system: str | None = None,
    known_systems: dict[str, list[str]] | None = None,
) -> tuple[list[str], str, str | None]:
    """Extract text and chunk a PDF without upserting.

    Returns (chunks, game_system, error_message).
    error_message is None on success.
    """
    if not pdf_path.exists():
        return [], "unknown", f"{pdf_path.name}: File not found"

    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        if not text.strip():
            return [], "unknown", f"{pdf_path.name}: Empty or scanned PDF"

        resolved_system = game_system or detect_game_system(
            pdf_path, text, known_systems=known_systems
        )
        chunks = chunk_text(text)
        return chunks, resolved_system, None

    except Exception as e:
        return [], "unknown", f"{pdf_path.name}: {str(e)}"


def compact_sqlite(data_dir: Path) -> int:
    """Run VACUUM on the ChromaDB SQLite database to reclaim disk space.

    Returns bytes reclaimed, or 0 if compaction was skipped.
    """
    if not data_dir:
        return 0
    sqlite_path = data_dir / "chroma.sqlite3"
    if not sqlite_path.exists():
        return 0

    import sqlite3

    size_before = os.path.getsize(sqlite_path)
    conn = sqlite3.connect(str(sqlite_path))
    conn.execute("VACUUM")
    conn.close()
    return size_before - os.path.getsize(sqlite_path)


def delete_source_chunks(source_path: str, collection) -> int:
    """Delete all chunks for a given source path from ChromaDB.

    Uses the full ``source`` metadata field to avoid collisions when two PDFs
    share the same filename in different directories.

    Returns the number of deleted chunks, or 0 if not found.
    """
    results = collection.get(where={"source": source_path}, include=[])
    ids_to_delete = results["ids"]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)

    return len(ids_to_delete)


def compute_diff(
    selected_paths: list[str], manifest: IndexManifest
) -> dict[str, list[dict]]:
    """Compare selected paths against the manifest to find what changed.

    Returns a dict with keys: to_add, to_remove, to_rename, to_update,
    up_to_date, errors.  Each value is a list of dicts describing the file.
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
                    })
                else:
                    up_to_date.append({
                        "path": path_str,
                        "filename": path.name,
                        "chunk_count": entry.chunk_count,
                        "game_system": entry.game_system,
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
            })

    # Files in manifest but no longer selected → to_remove
    to_remove += [
        {
            "path": path_str,
            "filename": manifest.files[path_str].filename,
            "chunk_count": manifest.files[path_str].chunk_count,
            "game_system": manifest.files[path_str].game_system,
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

def create_app(collection=None, data_dir: Path | None = None):
    """Create the FastAPI app, optionally with a pre-configured collection.

    In production: called with no arguments — sets up Ollama + PersistentClient.
    In tests: called with a test collection (EphemeralClient + ONNX embeddings).

    This pattern is called "dependency injection." The endpoints don't care
    HOW the collection was created — they just use it. This lets tests swap
    in a lightweight in-memory collection without needing Ollama running.

    Args:
        collection: ChromaDB collection (None = production auto-setup).
        data_dir: Directory for ChromaDB and manifest storage.
                  In production, resolved from --data-dir CLI arg.
                  In tests, pass tmp_path.
    """
    if collection is None:
        # Production path: same setup as before, but now only runs
        # when the server is actually started (not at import time).
        args = parse_args()
        data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"
        data_dir.mkdir(parents=True, exist_ok=True)

        chroma_client = chromadb.PersistentClient(path=str(data_dir))
        ollama_ef = embedding_functions.OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name="nomic-embed-text"
        )
        collection = chroma_client.get_or_create_collection(
            name="ttrpg_docs",
            embedding_function=ollama_ef
        )

    app = FastAPI(title="Legend Lore Sidecar")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Concurrency guard — prevents two syncs from running simultaneously.
    # The streaming sync uses a synchronous generator, so we use a
    # threading.Lock rather than asyncio.Lock.
    _sync_lock = threading.Lock()

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

    @app.post("/api/index-files")
    async def index_files(request: IndexFilesRequest):
        """Index specific PDF files by path."""
        total = len(request.paths)
        indexed = 0
        errors = []
        manifest = load_manifest(data_dir) if data_dir else None

        for pdf_path_str in request.paths:
            pdf_path = Path(pdf_path_str)
            chunk_count, error, detected_system = index_single_pdf(
                pdf_path, collection, game_system=request.game_system,
                known_systems=_merged["known"],
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

    @app.post("/api/sync-index")
    async def sync_index(request: SyncIndexRequest):
        """Apply index changes: add new, remove deselected, re-index modified.

        This is the main reconciliation endpoint. It computes the diff
        between selected paths and the manifest, then:
        1. Deletes chunks for deselected files
        2. Indexes new and modified files
        3. Updates the manifest
        """
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already in progress"
            )
        try:
            return _do_sync(request)
        finally:
            _sync_lock.release()

    def _sync_core(request: SyncIndexRequest):
        """Core sync generator shared by both endpoints.

        Yields progress dicts with an ``event`` key (``started``, ``progress``,
        or ``complete``).  The ``complete`` event contains the full result.
        """
        manifest = load_manifest(data_dir)
        diff = compute_diff(request.selected_paths, manifest)

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
            deleted = delete_source_chunks(entry["path"], collection)
            del manifest.files[entry["path"]]
            save_manifest(data_dir, manifest)
            removed += 1
            files_done += 1
            chunks_total += deleted
            yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": entry["filename"], "phase": "remove"}

        # Phase 1a: Auto-remove files deleted from disk
        for entry in diff["to_auto_remove"]:
            deleted = delete_source_chunks(entry["path"], collection)
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
            chunks, detected_system, error = prepare_pdf(
                pdf_path, game_system=override,
                known_systems=_merged["known"],
            )
            if error:
                errors.append(error)
                files_done += 1
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}
            else:
                batch_idx = 0
                while batch_idx < len(chunks):
                    batch_size = random.randint(80, 120)
                    batch_chunks = chunks[batch_idx:batch_idx + batch_size]
                    batch_metadatas = [{
                        "source": str(pdf_path),
                        "filename": pdf_path.name,
                        "chunk": batch_idx + chunk_idx,
                        "game_system": detected_system,
                    } for chunk_idx in range(len(batch_chunks))]
                    prefix = chunk_id_prefix(pdf_path)
                    batch_ids = [
                        f"{prefix}_{batch_idx + chunk_idx}"
                        for chunk_idx in range(len(batch_chunks))
                    ]
                    collection.upsert(
                        documents=batch_chunks,
                        metadatas=batch_metadatas,
                        ids=batch_ids,
                    )
                    chunks_total += len(batch_chunks)
                    batch_idx += len(batch_chunks)
                    yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}
                added += 1
                files_done += 1
                manifest.files[entry["path"]] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=len(chunks),
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
                    content_hash=file_content_hash(pdf_path),
                    file_size=os.path.getsize(pdf_path),
                )
                save_manifest(data_dir, manifest)
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}

        # Phase 3: Re-index modified files (delete old chunks first to prevent orphans)
        for entry in diff["to_update"]:
            delete_source_chunks(entry["path"], collection)
            pdf_path = Path(entry["path"])
            override = (
                request.game_system_overrides.get(entry["path"])
                if request.game_system_overrides else None
            )
            chunks, detected_system, error = prepare_pdf(
                pdf_path, game_system=override,
                known_systems=_merged["known"],
            )
            if error:
                errors.append(error)
                files_done += 1
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
            else:
                batch_idx = 0
                while batch_idx < len(chunks):
                    batch_size = random.randint(80, 120)
                    batch_chunks = chunks[batch_idx:batch_idx + batch_size]
                    batch_metadatas = [{
                        "source": str(pdf_path),
                        "filename": pdf_path.name,
                        "chunk": batch_idx + chunk_idx,
                        "game_system": detected_system,
                    } for chunk_idx in range(len(batch_chunks))]
                    prefix = chunk_id_prefix(pdf_path)
                    batch_ids = [
                        f"{prefix}_{batch_idx + chunk_idx}"
                        for chunk_idx in range(len(batch_chunks))
                    ]
                    collection.upsert(
                        documents=batch_chunks,
                        metadatas=batch_metadatas,
                        ids=batch_ids,
                    )
                    chunks_total += len(batch_chunks)
                    batch_idx += len(batch_chunks)
                    yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
                updated += 1
                files_done += 1
                manifest.files[entry["path"]] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=len(chunks),
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
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
                        coll_changed = True

            if auto_removed > 0:
                removed_paths = {e["path"] for e in diff["to_auto_remove"]}
                for coll in coll_store.collections.values():
                    filtered = [p for p in coll.file_paths if p not in removed_paths]
                    if len(filtered) != len(coll.file_paths):
                        coll.file_paths = filtered
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
        """Run sync and return the final result dict."""
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

    @app.post("/api/sync-index-stream")
    async def sync_index_stream(request: SyncIndexRequest):
        """Streaming version of sync-index that emits SSE progress events."""
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already in progress"
            )
        if not data_dir:
            _sync_lock.release()
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        def generate():
            for event in _sync_core(request):
                yield f"data: {json.dumps(event)}\n\n"

        def generate_with_lock():
            try:
                yield from generate()
            finally:
                _sync_lock.release()

        return StreamingResponse(generate_with_lock(), media_type="text/event-stream")

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
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already running"
            )
        try:
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
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {"renamed": True, "affected_collections": affected_collections}
        finally:
            _sync_lock.release()

    class FileDeleteRequest(BaseModel):
        path: str

    @app.post("/api/file-delete")
    async def file_delete(request: FileDeleteRequest):
        """Remove a single file's index entry immediately.

        Deletes chunks from ChromaDB and cleans up the manifest and
        collections.
        """
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already running"
            )
        try:
            if not data_dir:
                raise HTTPException(
                    status_code=500, detail="No data directory configured"
                )

            manifest = load_manifest(data_dir)
            path_str = request.path

            if path_str not in manifest.files:
                return {"deleted": False, "reason": "not_indexed"}

            delete_source_chunks(path_str, collection)
            del manifest.files[path_str]
            save_manifest(data_dir, manifest)

            # Update collections
            affected_collections = 0
            coll_store = load_collections(data_dir)
            for coll in coll_store.collections.values():
                if path_str in coll.file_paths:
                    coll.file_paths = [p for p in coll.file_paths if p != path_str]
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {"deleted": True, "affected_collections": affected_collections}
        finally:
            _sync_lock.release()

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
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already running"
            )
        try:
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
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {
                "renamed_files": renamed_files,
                "affected_collections": affected_collections,
            }
        finally:
            _sync_lock.release()

    @app.post("/api/folder-delete")
    async def folder_delete(request: FolderDeleteRequest):
        """Batch-delete all indexed files under a folder prefix.

        Removes chunks from ChromaDB and cleans up the manifest and
        collections.
        """
        if not _sync_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="A sync operation is already running"
            )
        try:
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
                delete_source_chunks(path_str, collection)
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
                    affected_collections += 1
            if affected_collections:
                save_collections(data_dir, coll_store)

            return {
                "deleted_files": deleted_files,
                "affected_collections": affected_collections,
            }
        finally:
            _sync_lock.release()

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

            # Calculate reclaimable space from SQLite freelist
            reclaimable_bytes = 0
            if data_dir:
                sqlite_path = data_dir / "chroma.sqlite3"
                if sqlite_path.exists():
                    import sqlite3
                    conn = sqlite3.connect(str(sqlite_path))
                    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
                    freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
                    conn.close()
                    reclaimable_bytes = page_size * freelist

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
        """Compact the ChromaDB database to reclaim disk space."""
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
        reclaimed = compact_sqlite(data_dir)

        return {
            "size_before": size_before,
            "size_after": size_before - reclaimed,
            "reclaimed": reclaimed,
        }

    @app.get("/api/sources")
    async def get_sources():
        """List all indexed PDFs with chunk counts."""
        try:
            results = collection.get(include=["metadatas"])
            if not results["metadatas"]:
                return {"sources": [], "count": 0}

            sources_info = {}
            for metadata in results["metadatas"]:
                filename = metadata["filename"]
                if filename not in sources_info:
                    sources_info[filename] = {
                        "filename": filename,
                        "source": metadata.get("source", ""),
                        "chunks": 0,
                        "game_system": metadata.get("game_system", "unknown"),
                    }
                sources_info[filename]["chunks"] += 1

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
                    "is_builtin": e.get("is_builtin", True),
                    "is_customized": e.get("is_customized", False),
                }
                for e in _merged["list"]
            ],
            key=lambda s: s["tag"].lower(),
        )
        return {"systems": systems}

    @app.post("/api/set-game-system")
    async def set_game_system(request: SetGameSystemRequest):
        """Update the game system tag for all chunks of a file.

        Changes metadata in ChromaDB and the manifest without re-indexing.
        """
        try:
            # Look up the full source path from the manifest
            manifest = load_manifest(data_dir) if data_dir else None
            source_path = None
            if manifest:
                for path_str, entry in manifest.files.items():
                    if entry.filename == request.filename:
                        source_path = path_str
                        break

            if not source_path:
                raise HTTPException(
                    status_code=404,
                    detail=f"Source not found: {request.filename}",
                )

            results = collection.get(
                where={"source": source_path},
                include=["metadatas"],
            )

            if not results["ids"]:
                raise HTTPException(
                    status_code=404,
                    detail=f"Source not found: {request.filename}",
                )

            updated_metadatas = [
                {**metadata, "game_system": request.game_system}
                for metadata in results["metadatas"]
            ]

            collection.update(
                ids=results["ids"],
                metadatas=updated_metadatas,
            )

            if manifest:
                for entry in manifest.files.values():
                    if entry.filename == request.filename:
                        entry.game_system = request.game_system
                save_manifest(data_dir, manifest)

            return {
                "filename": request.filename,
                "game_system": request.game_system,
                "chunks_updated": len(results["ids"]),
            }
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
        ))
        if data_dir:
            save_custom_systems(data_dir, store)
        _rebuild_merged()

        return {
            "tag": request.tag,
            "keywords": request.keywords,
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
                found = True
                break

        if not found:
            # If it's a built-in, create a custom override
            builtin_tags = {e["tag"] for e in GAME_SYSTEMS}
            if tag in builtin_tags:
                store.systems.append(CustomGameSystemEntry(
                    tag=request.tag,
                    keywords=request.keywords,
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

            deleted = delete_source_chunks(source_path, collection)

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
                    "name": c.name,
                    "file_paths": c.file_paths,
                    "file_count": len(c.file_paths),
                    "created_at": c.created_at,
                    "description": c.description,
                }
                for name, c in store.collections.items()
            },
            "count": len(store.collections),
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
        store.collections[request.name] = Collection(
            name=request.name,
            file_paths=request.file_paths,
            created_at=datetime.now(timezone.utc).isoformat(),
            description=request.description,
        )
        save_collections(data_dir, store)
        return {"name": request.name, "file_count": len(request.file_paths)}

    @app.put("/api/collections/{name}")
    async def update_collection(name: str, request: UpdateCollectionRequest):
        """Update a collection's files or description."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        if name not in store.collections:
            raise HTTPException(
                status_code=404, detail=f"Collection not found: {name}"
            )
        store.collections[name].file_paths = request.file_paths
        if request.description is not None:
            store.collections[name].description = request.description
        save_collections(data_dir, store)
        return {"name": name, "file_count": len(request.file_paths)}

    @app.delete("/api/collections/{name}")
    async def delete_collection(name: str):
        """Delete a collection."""
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        store = load_collections(data_dir)
        if name not in store.collections:
            raise HTTPException(
                status_code=404, detail=f"Collection not found: {name}"
            )
        del store.collections[name]
        save_collections(data_dir, store)
        return {"message": f"Deleted collection: {name}"}

    @app.post("/api/search")
    async def search(request: SearchRequest):
        """Semantic search across indexed documents."""
        try:
            query_kwargs = {
                "query_texts": [request.query],
                "n_results": request.n_results,
            }

            where_clauses = []
            if request.collection:
                if not data_dir:
                    raise HTTPException(
                        status_code=500, detail="No data directory configured"
                    )
                store = load_collections(data_dir)
                if request.collection not in store.collections:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Collection not found: {request.collection}",
                    )
                manifest = load_manifest(data_dir)
                filenames = resolve_collection_filenames(
                    store.collections[request.collection], manifest
                )
                if not filenames:
                    return {"results": [], "message": "Collection has no indexed files."}
                where_clauses.append({"filename": {"$in": filenames}})
            if request.source_filter:
                where_clauses.append({"filename": request.source_filter})
            if request.game_system:
                where_clauses.append({"game_system": request.game_system})

            if len(where_clauses) == 1:
                query_kwargs["where"] = where_clauses[0]
            elif len(where_clauses) > 1:
                query_kwargs["where"] = {"$and": where_clauses}

            results = collection.query(**query_kwargs)

            if not results["documents"][0]:
                return {"results": [], "message": "No results found."}

            formatted = []
            for doc, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                formatted.append({
                    "text": doc,
                    "filename": metadata["filename"],
                    "source": metadata.get("source", ""),
                    "chunk": metadata.get("chunk", 0),
                    "game_system": metadata.get("game_system", "unknown"),
                    "relevance": round(1 - distance, 3)
                })

            return {"results": formatted}
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

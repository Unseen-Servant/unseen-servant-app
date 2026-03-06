"""
Unseen Servant — ChromaDB indexing sidecar.

Started automatically by the Tauri desktop app.
Provides HTTP endpoints for indexing PDFs and searching indexed content.

Usage:
    python server.py --port 8420 --data-dir /path/to/app/data
"""

import argparse
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
    parser = argparse.ArgumentParser(description="Unseen Servant indexing sidecar")
    parser.add_argument("--port", type=int, default=8420, help="HTTP port")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Directory for ChromaDB storage (default: ./chroma_db)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pure helpers (no dependencies — safe to import in tests)
# ---------------------------------------------------------------------------

from game_systems import GAME_SYSTEMS, KNOWN_SYSTEMS


def detect_game_system(pdf_path: Path, text: str | None = None) -> str:
    """Detect the TTRPG game system from folder path or PDF content.

    Detection priority:
    1. Folder name match (user's deliberate organization)
    2. Content keyword match (first 2000 chars of extracted text)
    3. Fallback to "unknown"
    """
    # Check path components (folder names)
    path_lower = str(pdf_path).lower()
    for system, keywords in KNOWN_SYSTEMS.items():
        for keyword in keywords:
            if keyword in path_lower:
                return system

    # Check content if provided
    if text:
        text_sample = text[:2000].lower()
        for system, keywords in KNOWN_SYSTEMS.items():
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
    """Write the index manifest to disk."""
    manifest_path = data_dir / MANIFEST_FILENAME
    manifest_path.write_text(manifest.model_dump_json(indent=2))


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
    """Write collections to disk."""
    path = data_dir / COLLECTIONS_FILENAME
    path.write_text(store.model_dump_json(indent=2))


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

def index_single_pdf(
    pdf_path: Path, collection, game_system: str | None = None
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

        resolved_system = game_system or detect_game_system(pdf_path, text)
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
            batch_ids = [
                f"{pdf_path.stem}_{batch_idx + chunk_idx}"
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
    pdf_path: Path, game_system: str | None = None
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

        resolved_system = game_system or detect_game_system(pdf_path, text)
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


def delete_source_chunks(filename: str, collection) -> int:
    """Delete all chunks for a given filename from ChromaDB.

    Returns the number of deleted chunks, or 0 if not found.
    """
    results = collection.get(where={"filename": filename}, include=[])
    ids_to_delete = results["ids"]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)

    return len(ids_to_delete)


def compute_diff(
    selected_paths: list[str], manifest: IndexManifest
) -> dict[str, list[dict]]:
    """Compare selected paths against the manifest to find what changed.

    Returns a dict with keys: to_add, to_remove, to_update, up_to_date, errors.
    Each value is a list of dicts describing the file.
    """
    selected = set(selected_paths)
    indexed = set(manifest.files.keys())

    to_add = []
    to_update = []
    up_to_date = []
    errors = []

    for path_str in selected:
        path = Path(path_str)
        if path_str not in indexed:
            # New file — not yet indexed
            if not path.exists():
                errors.append({"path": path_str, "error": "File not found on disk"})
            else:
                to_add.append({"path": path_str, "filename": path.name})
        else:
            # Already indexed — check if modified
            entry = manifest.files[path_str]
            if not path.exists():
                errors.append({"path": path_str, "error": "File not found on disk"})
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

    # Files in manifest but no longer selected → to_remove
    to_remove = [
        {
            "path": path_str,
            "filename": manifest.files[path_str].filename,
            "chunk_count": manifest.files[path_str].chunk_count,
            "game_system": manifest.files[path_str].game_system,
        }
        for path_str in (indexed - selected)
    ]

    return {
        "to_add": to_add,
        "to_remove": to_remove,
        "to_update": to_update,
        "up_to_date": up_to_date,
        "errors": errors,
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

    app = FastAPI(title="Unseen Servant Sidecar")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
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
                pdf_path, collection, game_system=request.game_system
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
                "update": len(diff["to_update"]),
                "up_to_date": len(diff["up_to_date"]),
                "errors": len(diff["errors"]),
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
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        manifest = load_manifest(data_dir)
        diff = compute_diff(request.selected_paths, manifest)

        removed = 0
        added = 0
        updated = 0
        errors = []

        # Phase 1: Remove deselected files
        for entry in diff["to_remove"]:
            delete_source_chunks(entry["filename"], collection)
            del manifest.files[entry["path"]]
            removed += 1

        # Phase 2: Index new files
        for entry in diff["to_add"]:
            pdf_path = Path(entry["path"])
            override = (
                request.game_system_overrides.get(entry["path"])
                if request.game_system_overrides else None
            )
            chunk_count, error, detected_system = index_single_pdf(
                pdf_path, collection, game_system=override
            )
            if error:
                errors.append(error)
            else:
                added += 1
                manifest.files[entry["path"]] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=chunk_count,
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
                )

        # Phase 3: Re-index modified files (delete old chunks first to prevent orphans)
        for entry in diff["to_update"]:
            delete_source_chunks(entry["filename"], collection)
            pdf_path = Path(entry["path"])
            override = (
                request.game_system_overrides.get(entry["path"])
                if request.game_system_overrides else None
            )
            chunk_count, error, detected_system = index_single_pdf(
                pdf_path, collection, game_system=override
            )
            if error:
                errors.append(error)
            else:
                updated += 1
                manifest.files[entry["path"]] = ManifestEntry(
                    filename=pdf_path.name,
                    mtime=os.path.getmtime(pdf_path),
                    chunk_count=chunk_count,
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                    game_system=detected_system,
                )

        save_manifest(data_dir, manifest)

        if removed > 0 or updated > 0:
            compact_sqlite(data_dir)

        return {
            "added": added,
            "removed": removed,
            "updated": updated,
            "errors": errors,
            "total_indexed": len(manifest.files),
        }

    @app.post("/api/sync-index-stream")
    async def sync_index_stream(request: SyncIndexRequest):
        """Streaming version of sync-index that emits SSE progress events."""
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )

        def _progress_event(files_done, total_files, chunks_total, current_file, phase):
            return f"data: {json.dumps({'event': 'progress', 'files_done': files_done, 'total_files': total_files, 'chunks_total': chunks_total, 'current_file': current_file, 'phase': phase})}\n\n"

        def generate():
            manifest = load_manifest(data_dir)
            diff = compute_diff(request.selected_paths, manifest)

            total_files = (
                len(diff["to_remove"])
                + len(diff["to_add"])
                + len(diff["to_update"])
            )
            files_done = 0
            chunks_total = 0
            removed = 0
            added = 0
            updated = 0
            errors = []

            yield f"data: {json.dumps({'event': 'started', 'total_files': total_files})}\n\n"

            # Phase 1: Remove deselected files
            for entry in diff["to_remove"]:
                deleted = delete_source_chunks(entry["filename"], collection)
                del manifest.files[entry["path"]]
                removed += 1
                files_done += 1
                chunks_total += deleted
                yield _progress_event(files_done, total_files, chunks_total, entry["filename"], "remove")

            # Phase 2: Index new files
            for entry in diff["to_add"]:
                pdf_path = Path(entry["path"])
                override = (
                    request.game_system_overrides.get(entry["path"])
                    if request.game_system_overrides else None
                )
                chunks, detected_system, error = prepare_pdf(
                    pdf_path, game_system=override
                )
                if error:
                    errors.append(error)
                    files_done += 1
                    yield _progress_event(files_done, total_files, chunks_total, pdf_path.name, "add")
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
                        batch_ids = [
                            f"{pdf_path.stem}_{batch_idx + chunk_idx}"
                            for chunk_idx in range(len(batch_chunks))
                        ]
                        collection.upsert(
                            documents=batch_chunks,
                            metadatas=batch_metadatas,
                            ids=batch_ids,
                        )
                        chunks_total += len(batch_chunks)
                        batch_idx += len(batch_chunks)
                        yield _progress_event(files_done, total_files, chunks_total, pdf_path.name, "add")
                    added += 1
                    files_done += 1
                    manifest.files[entry["path"]] = ManifestEntry(
                        filename=pdf_path.name,
                        mtime=os.path.getmtime(pdf_path),
                        chunk_count=len(chunks),
                        indexed_at=datetime.now(timezone.utc).isoformat(),
                        game_system=detected_system,
                    )
                    yield _progress_event(files_done, total_files, chunks_total, pdf_path.name, "add")

            # Phase 3: Re-index modified files (delete old chunks first to prevent orphans)
            for entry in diff["to_update"]:
                delete_source_chunks(entry["filename"], collection)
                pdf_path = Path(entry["path"])
                override = (
                    request.game_system_overrides.get(entry["path"])
                    if request.game_system_overrides else None
                )
                chunks, detected_system, error = prepare_pdf(
                    pdf_path, game_system=override
                )
                if error:
                    errors.append(error)
                    files_done += 1
                    yield _progress_event(files_done, total_files, chunks_total, pdf_path.name, "update")
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
                        batch_ids = [
                            f"{pdf_path.stem}_{batch_idx + chunk_idx}"
                            for chunk_idx in range(len(batch_chunks))
                        ]
                        collection.upsert(
                            documents=batch_chunks,
                            metadatas=batch_metadatas,
                            ids=batch_ids,
                        )
                        chunks_total += len(batch_chunks)
                        batch_idx += len(batch_chunks)
                        yield _progress_event(files_done, total_files, chunks_total, pdf_path.name, "update")
                    updated += 1
                    files_done += 1
                    manifest.files[entry["path"]] = ManifestEntry(
                        filename=pdf_path.name,
                        mtime=os.path.getmtime(pdf_path),
                        chunk_count=len(chunks),
                        indexed_at=datetime.now(timezone.utc).isoformat(),
                        game_system=detected_system,
                    )
                    yield _progress_event(files_done, total_files, chunks_total, pdf_path.name, "update")

            save_manifest(data_dir, manifest)

            if removed > 0 or updated > 0:
                compact_sqlite(data_dir)

            yield f"data: {json.dumps({'event': 'complete', 'added': added, 'removed': removed, 'updated': updated, 'errors': errors, 'total_indexed': len(manifest.files), 'chunks_total': chunks_total})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

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
            return {
                "total_chunks": count,
                "total_documents": unique_sources,
                "collection_name": collection.name,
                "storage_bytes": storage_bytes,
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
        """Return all predefined game systems from game_systems.py."""
        systems = sorted(
            [{"tag": e["tag"], "game_system": e["game_system"]} for e in GAME_SYSTEMS],
            key=lambda s: s["tag"].lower(),
        )
        return {"systems": systems}

    @app.post("/api/set-game-system")
    async def set_game_system(request: SetGameSystemRequest):
        """Update the game system tag for all chunks of a file.

        Changes metadata in ChromaDB and the manifest without re-indexing.
        """
        try:
            results = collection.get(
                where={"filename": request.filename},
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

            if data_dir:
                manifest = load_manifest(data_dir)
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

    @app.delete("/api/source/{filename}")
    async def delete_source(filename: str):
        """Delete a source and all its chunks."""
        try:
            deleted = delete_source_chunks(filename, collection)

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

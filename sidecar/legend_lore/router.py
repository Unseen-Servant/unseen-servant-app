"""
Legend Lore's HTTP routes, mounted by ``sidecar/server.py``.
"""

import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .chunker import PIPELINE_VERSION
from .game_systems import GAME_SYSTEMS
from .granularity import build as build_granularity
from .lexical import PersistedLexicalIndex
from .parents_store import (
    clear_all_parents,
    count_units_fts,
    fetch_section_by_id,
    rename_source,
    update_units_fts_game_system,
)
from .service import (
    _atomic_index_pdf,
    chunk_id_prefix,
    Collection,
    COLLECTION_METADATA,
    compact_sqlite,
    compute_diff,
    _compute_reclaimable_bytes,
    CreateCollectionRequest,
    CustomGameSystemEntry,
    CustomGameSystemRequest,
    CustomGameSystemsStore,
    delete_source_chunks,
    EmbedBatchError,
    file_content_hash,
    gc_orphan_segments,
    get_merged_systems,
    index_single_pdf,
    IndexFilesRequest,
    IndexManifest,
    IndexStatusRequest,
    load_collections,
    load_custom_systems,
    load_manifest,
    load_search_settings,
    manifest_digest,
    ManifestEntry,
    _mark_manifest_error,
    METADATA_UPDATE_BATCH_SIZE,
    _now_iso,
    _page_labels,
    prepare_pdf,
    ReindexFileRequest,
    _remove_segment_dir,
    RenameCollectionRequest,
    save_collections,
    save_custom_systems,
    save_manifest,
    save_search_settings,
    _search_sync,
    SearchRequest,
    SearchSettings,
    SearchSettingsUpdate,
    _segment_ids_for_collection,
    SetGameSystemRequest,
    SetGameSystemsRequest,
    SyncIndexRequest,
    ToggleBuiltinRequest,
    UpdateCollectionRequest,
)
from .spelling import SpellCorrector


def build_router(
    app,
    collection,
    data_dir: Path | None,
    chroma_client=None,
    embedding_function=None,
) -> APIRouter:
    """Build the Legend Lore routes over ``collection`` and ``data_dir``.

    The routes close over the factory arguments exactly as they did when
    they lived inside ``create_app``; ``app`` is passed for its ``state``
    (MCP activity stamp, the spell-corrector hook for the boot warm-up).
    """
    router = APIRouter()

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

    @router.post("/api/index-files")
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
                        pipeline_version=PIPELINE_VERSION,
                    )

        if manifest and data_dir:
            save_manifest(data_dir, manifest)

        return {
            "indexed": indexed,
            "total": total,
            "errors": errors
        }

    @router.post("/api/reindex-file")
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

            # Atomic: index_single_pdf stages new chunks under a fresh prefix
            # and only swaps in once embedding succeeds. Old chunks/parents
            # remain on failure so search keeps working.
            chunk_count, error, detected_system, detected_systems = index_single_pdf(
                pdf_path, collection, game_system=request.game_system,
                known_systems=_merged["known"], data_dir=data_dir,
            )

            if error:
                if data_dir:
                    manifest = load_manifest(data_dir)
                    _mark_manifest_error(manifest, data_dir, request.path, error)
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
                    pipeline_version=PIPELINE_VERSION,
                )
                save_manifest(data_dir, manifest)

            return {
                "chunks": chunk_count,
                "game_system": detected_system,
                "error": None,
            }

    @router.post("/api/index-status")
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
                "outdated": len(diff["outdated"]),
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
                # Ids rebuild from the stored ordinal, not the list
                # position, so they match what rename_source writes to
                # the FTS rows.
                new_ids = [f"{prefix}_{m['chunk']}" for m in results["metadatas"]]
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
                rename_source(
                    data_dir, old_path_str, str(new_path), new_path.name, prefix
                )
                transferred = len(results["ids"])

            old_entry = manifest.files[old_path_str]
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
                pipeline_version=old_entry.pipeline_version,
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
                continue

            embed_units, parents = build_granularity(chunks)
            try:
                for n in _atomic_index_pdf(
                    pdf_path, detected_system, embed_units, parents,
                    collection, data_dir, page_labels=_page_labels(pdf_path),
                ):
                    chunks_total += n
                    yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}
            except EmbedBatchError as e:
                # Partial new chunks already rolled back by _atomic_index_pdf.
                # No prior manifest entry exists for an add; just record the
                # error so the user sees it. Next sync will retry.
                err_msg = str(e)
                errors.append(err_msg)
                files_done += 1
                yield {"event": "error", "file": pdf_path.name, "message": err_msg, "phase": "add"}
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}
                continue

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
                pipeline_version=PIPELINE_VERSION,
            )
            save_manifest(data_dir, manifest)
            yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "add"}

        # Phase 3: Re-index modified files. Atomic — old chunks are only
        # removed once the new ones land. On failure, the previous
        # successful manifest entry is preserved with last_error set.
        for entry in diff["to_update"]:
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
                _mark_manifest_error(manifest, data_dir, entry["path"], error)
                yield {"event": "error", "file": pdf_path.name, "message": error, "phase": "update"}
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
                continue

            embed_units, parents = build_granularity(chunks)
            try:
                for n in _atomic_index_pdf(
                    pdf_path, detected_system, embed_units, parents,
                    collection, data_dir, page_labels=_page_labels(pdf_path),
                ):
                    chunks_total += n
                    yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
            except EmbedBatchError as e:
                err_msg = str(e)
                errors.append(err_msg)
                files_done += 1
                _mark_manifest_error(manifest, data_dir, entry["path"], err_msg)
                yield {"event": "error", "file": pdf_path.name, "message": err_msg, "phase": "update"}
                yield {"event": "progress", "files_done": files_done, "total_files": total_files, "chunks_total": chunks_total, "current_file": pdf_path.name, "phase": "update"}
                continue

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
                pipeline_version=PIPELINE_VERSION,
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

    @router.post("/api/sync-index")
    async def sync_index(request: SyncIndexRequest):
        """Apply index changes synchronously (test convenience endpoint).

        Production code uses ``/api/sync-index-stream`` for SSE progress.
        """
        with sync_lock_or_409():
            return _do_sync(request)

    @router.post("/api/sync-index-stream")
    async def sync_index_stream(request: SyncIndexRequest):
        """Streaming version of sync-index that emits SSE progress events.

        Acquires the sync lock synchronously so 409 surfaces as a normal
        HTTP error. Once the lock is held, the only release path is the
        generator's ``finally`` — so any intermediate validation must run
        before the acquire to avoid leaking the lock.
        """
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )
        acquire_sync_lock_or_409()

        def generate_with_lock():
            try:
                for event in _sync_core(request):
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                _sync_lock.release()

        return StreamingResponse(generate_with_lock(), media_type="text/event-stream")

    @router.post("/api/reindex-all-stream")
    async def reindex_all_stream():
        """Force re-extraction and re-embedding of every indexed file.

        Streams the same SSE progress events as ``/api/sync-index-stream``.
        Reuses the sync pipeline with ``force=True`` over all currently
        indexed paths, so unchanged-on-disk files are re-processed with the
        current extractor.
        """
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )
        acquire_sync_lock_or_409()

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

    @router.post("/api/delete-index")
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
                    metadata=COLLECTION_METADATA,
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

    @router.post("/api/file-rename")
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
                # Ordinal-derived ids: see the sync rename phase.
                new_ids = [f"{prefix}_{m['chunk']}" for m in results["metadatas"]]
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
                rename_source(
                    data_dir, old_path_str, new_path_str, new_path.name, prefix
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
                pipeline_version=old_entry.pipeline_version,
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

    @router.post("/api/file-delete")
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

    @router.post("/api/folder-rename")
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
                    # Ordinal-derived ids: see the sync rename phase.
                    new_ids = [
                        f"{prefix}_{m['chunk']}" for m in results["metadatas"]
                    ]
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
                    rename_source(
                        data_dir, old_path_str, new_path_str,
                        new_path.name, prefix,
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
                    pipeline_version=old_entry.pipeline_version,
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

    @router.post("/api/folder-delete")
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

    @router.get("/api/stats")
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

    @router.post("/api/compact")
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

    @router.get("/api/search-settings")
    async def get_search_settings():
        """Current sidecar-wide search-pipeline settings."""
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )
        return load_search_settings(data_dir).model_dump()

    @router.put("/api/search-settings")
    async def put_search_settings(update: SearchSettingsUpdate):
        """Merge a partial update into the persisted search settings.

        Values are validated/clamped by SearchSettings and echoed back so
        the UI can adopt what was actually stored.
        """
        if not data_dir:
            raise HTTPException(
                status_code=500, detail="No data directory configured"
            )
        current = load_search_settings(data_dir).model_dump()
        current.update(
            {k: v for k, v in update.model_dump().items() if v is not None}
        )
        settings = SearchSettings(**current)
        save_search_settings(data_dir, settings)
        return settings.model_dump()

    @router.get("/api/sources")
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
                source_path = metadata.get("source", "")
                # Key by source path, not filename: same-named PDFs in
                # different folders are distinct sources and would
                # otherwise merge into one entry (issue #308 family).
                key = source_path or filename
                if key not in sources_info:
                    entry = manifest.files.get(source_path)
                    primary = metadata.get("game_system", "unknown")
                    if entry and entry.game_systems:
                        systems = list(entry.game_systems)
                    elif primary != "unknown":
                        systems = [primary]
                    else:
                        systems = []
                    sources_info[key] = {
                        "filename": filename,
                        "source": source_path,
                        "chunks": 0,
                        "game_system": primary,
                        "game_systems": systems,
                        "pages": 0,
                        "indexed_at": entry.indexed_at if entry else None,
                        "file_size_bytes": entry.file_size if entry else None,
                    }
                sources_info[key]["chunks"] += 1
                page_end = metadata.get("page_end")
                if isinstance(page_end, int) and page_end > sources_info[key]["pages"]:
                    sources_info[key]["pages"] = page_end

            sources_list = sorted(sources_info.values(), key=lambda x: x["filename"])
            return {"sources": sources_list, "count": len(sources_list)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/game-systems")
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

    @router.get("/api/known-game-systems")
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

    def _resolve_source(manifest, filename: str | None, path: str | None) -> str:
        """Return the manifest path a mutation targets.

        ``path`` is exact. A bare ``filename`` is accepted only while it
        names one indexed file: same-named twins in different folders are
        refused with 409 rather than guessed at (#330).
        """
        if path is not None:
            if path not in manifest.files:
                raise HTTPException(status_code=404, detail=f"Source not found: {path}")
            return path
        matches = [p for p, e in manifest.files.items() if e.filename == filename]
        if not matches:
            raise HTTPException(status_code=404, detail=f"Source not found: {filename}")
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail=f"{len(matches)} indexed files are named {filename}; address one by path",
            )
        return matches[0]

    def _apply_game_systems(
        filename: str | None, game_systems: list[str], path: str | None = None
    ) -> dict:
        """Update Chroma chunk metadata + manifest entry for a file's tags.

        ``game_systems[0]`` becomes the primary scalar in chunk metadata
        (and the manifest's ``game_system`` field). The full list is
        written to the manifest's ``game_systems`` field. An empty list
        clears both back to ``"unknown"`` / ``[]``.
        """
        primary = game_systems[0] if game_systems else "unknown"

        if not data_dir:
            raise HTTPException(
                status_code=404,
                detail=f"Source not found: {path or filename}",
            )
        manifest = load_manifest(data_dir)
        source_path = _resolve_source(manifest, filename, path)
        entry = manifest.files[source_path]

        results = collection.get(
            where={"source": source_path},
            include=["metadatas"],
        )

        if not results["ids"]:
            raise HTTPException(
                status_code=404,
                detail=f"Source not found: {source_path}",
            )

        updated_metadatas = [
            {**metadata, "game_system": primary}
            for metadata in results["metadatas"]
        ]

        # One call per slice: a file's chunk count routinely exceeds Chroma's
        # per-write cap, and going over it fails the whole update.
        for start in range(0, len(results["ids"]), METADATA_UPDATE_BATCH_SIZE):
            end = start + METADATA_UPDATE_BATCH_SIZE
            collection.update(
                ids=results["ids"][start:end],
                metadatas=updated_metadatas[start:end],
            )

        update_units_fts_game_system(data_dir, source_path, primary)

        entry.game_system = primary
        entry.game_systems = list(game_systems)
        save_manifest(data_dir, manifest)

        return {
            "filename": entry.filename,
            "game_system": primary,
            "game_systems": list(game_systems),
            "chunks_updated": len(results["ids"]),
        }

    @router.post("/api/set-game-system")
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

    @router.post("/api/set-game-systems")
    async def set_game_systems(request: SetGameSystemsRequest):
        """Update multiple game system tags for all chunks of a file.

        The first tag becomes the primary stored in ChromaDB metadata; the
        full list is persisted to the manifest. An empty list clears all
        tags back to ``"unknown"``.
        """
        try:
            if request.path is None and request.filename is None:
                raise HTTPException(status_code=422, detail="path or filename is required")
            return _apply_game_systems(
                request.filename, request.game_systems, path=request.path
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------------------------------
    # Custom game system CRUD
    # ------------------------------------------------------------------

    @router.post("/api/custom-game-systems")
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

    @router.put("/api/custom-game-systems/{tag}")
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

    @router.delete("/api/custom-game-systems/{tag}")
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

    @router.post("/api/custom-game-systems/toggle-builtin")
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

    @router.delete("/api/source/{filename}")
    async def delete_source(filename: str):
        """Delete a source and all its chunks."""
        try:
            # Look up the full path from the manifest so we can filter by source
            manifest = load_manifest(data_dir)
            source_path = _resolve_source(manifest, filename, None)

            deleted = delete_source_chunks(source_path, collection, data_dir=data_dir)

            if not deleted:
                raise HTTPException(status_code=404, detail=f"Source not found: {filename}")

            compact_sqlite(data_dir)

            return {"message": f"Deleted {deleted} chunks from {filename}"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/source/{filename}/content")
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

    @router.get("/api/section/{section_id}")
    async def get_section(section_id: str):
        """Fetch one assembled section by its id (a search result's `section_id`).

        Drill-in counterpart to the compact search results the MCP tool
        returns by default: the model pulls the full section text only
        when it needs it, instead of paying its cost on every result.
        """
        sec = fetch_section_by_id(data_dir, section_id) if data_dir else None
        if sec is None:
            raise HTTPException(
                status_code=404, detail=f"Section not found: {section_id}"
            )

        return {
            "section_id": sec.section_id,
            "section_heading": sec.section_heading or "",
            "text": sec.text,
            "filename": Path(sec.source_pdf).name,
            "source": sec.source_pdf,
            "page_start": sec.page_start,
            "page_end": sec.page_end,
            # False means "this is the whole section"; True means the
            # assembly cap forced a window around the match.
            "windowed": sec.windowed,
        }

    @router.get("/api/source/{filename}/pages")
    async def get_source_pages(
        filename: str,
        start: int = Query(..., ge=1),
        end: int = Query(..., ge=1),
    ):
        """Fetch the raw text of a page range directly from the PDF.

        Resolves `filename` through the manifest, like `/content` does.
        Another drill-in for the MCP tools: content a section-based search
        doesn't surface well (a table of contents, a map, an appendix).
        """
        if end < start or end - start > 20:
            raise HTTPException(
                status_code=400,
                detail="end must be >= start and span at most 20 pages",
            )

        manifest = load_manifest(data_dir) if data_dir else IndexManifest()
        source_path = None
        for path_str, entry in manifest.files.items():
            if entry.filename == filename:
                source_path = path_str
                break

        if not source_path:
            raise HTTPException(
                status_code=404, detail=f"Source not found: {filename}"
            )

        try:
            doc = pymupdf.open(source_path)
        except Exception:
            raise HTTPException(
                status_code=404, detail=f"Source not found: {filename}"
            )

        try:
            if start > doc.page_count:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Page {start} is beyond the last page "
                        f"({doc.page_count}) of {filename}"
                    ),
                )
            lo = max(1, start)
            hi = min(doc.page_count, end)
            text = "\n\n".join(
                doc[p - 1].get_text("text") for p in range(lo, hi + 1)
            )
        finally:
            doc.close()

        return {"filename": filename, "start": lo, "end": hi, "text": text}

    # ------------------------------------------------------------------
    # Collections endpoints
    # ------------------------------------------------------------------

    @router.get("/api/collections")
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
        }

    @router.post("/api/collections")
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

    @router.put("/api/collections/{name}")
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

    @router.delete("/api/collections/{name}")
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

    @router.post("/api/collections/{name}/rename")
    async def rename_collection(name: str, request: RenameCollectionRequest):
        """Atomically rename a collection.

        Preserves all metadata (id, file_paths, color, archived, timestamps).
        Frontend used to do delete + create which lost the collection on
        partial failure.
        """
        if not data_dir:
            raise HTTPException(status_code=500, detail="No data directory configured")
        new_name = request.new_name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="New name cannot be empty")
        store = load_collections(data_dir)
        if name not in store.collections:
            raise HTTPException(
                status_code=404, detail=f"Collection not found: {name}"
            )
        if new_name == name:
            coll = store.collections[name]
            return {"name": name, "file_count": len(coll.file_paths)}
        if new_name in store.collections:
            raise HTTPException(
                status_code=409, detail=f"Collection already exists: {new_name}"
            )
        coll = store.collections.pop(name)
        coll.name = new_name
        coll.updated_at = _now_iso()
        store.collections[new_name] = coll
        save_collections(data_dir, store)
        return {"name": new_name, "file_count": len(coll.file_paths)}

    # Experimental BM25 hybrid (default-off `hybrid` search flag): the
    # lexical rows are written at index time into the parents SQLite, so
    # there is nothing to build, cache or invalidate here. Constructed per
    # call — it is two attributes, and `collection` is rebound when
    # /api/delete-index recreates the collection, so a handle captured
    # once would go stale.
    def _get_lexical_index() -> PersistedLexicalIndex:
        return PersistedLexicalIndex(data_dir, collection)

    # Spell-correction vocabulary: built lazily on first use (and at boot
    # by ``warm_search_stack``), rebuilt when the index changes. On an
    # indexed library the key is the manifest digest, so a re-index that
    # happens to leave the chunk count unchanged still invalidates it;
    # with nothing indexed the chunk count is all there is (issue #343).
    #
    # Where the vocabulary is read from is decided once per key, on a
    # cache miss, by coverage: the persisted FTS rows only when they
    # cover every indexed chunk, otherwise the full Chroma scan.
    # All-or-nothing because a part-migrated library's FTS rows are a
    # subset of the library — building from them would leave the
    # un-migrated books' proper nouns out of the vocabulary, and
    # ``correct()`` would rewrite them as typos. That is a change in
    # search results, which this path must not make. Coverage is also
    # the reason the check is per-key: ``count_units_fts`` is an O(rows)
    # scan (~37 ms at 100k rows), and a per-search check would pay it
    # once per query — twice under variant expansion.
    #
    # The cache is guarded by a lock: since #344 the search body runs in
    # a worker thread, so two concurrent searches can race here on a
    # cold cache and each pay the full build cost.
    spell_cache: dict = {"key": None, "corrector": None, "mode": None}
    spell_lock = threading.Lock()

    def _get_spell_corrector(
        manifest: IndexManifest | None = None
    ) -> SpellCorrector:
        """``manifest`` is the caller's already-loaded manifest, so the
        search path does not re-read it just to check the cache key."""
        expected_units = 0
        if data_dir:
            if manifest is None:
                manifest = load_manifest(data_dir)
            expected_units = sum(
                e.chunk_count for e in manifest.files.values()
            )
        key = (
            manifest_digest(manifest) if expected_units
            else collection.count()
        )
        with spell_lock:
            if spell_cache["corrector"] is None or spell_cache["key"] != key:
                mode = (
                    "store"
                    if expected_units
                    and count_units_fts(data_dir) >= expected_units
                    else "chroma"
                )
                spell_cache["corrector"] = (
                    SpellCorrector.from_store(data_dir) if mode == "store"
                    else SpellCorrector.from_collection(collection)
                )
                spell_cache["key"] = key
                spell_cache["mode"] = mode
            return spell_cache["corrector"]

    # Exposed for the boot warm-up thread in __main__.
    app.state.get_spell_corrector = _get_spell_corrector

    @router.post("/api/search")
    async def search(request: SearchRequest, http_req: Request):
        """Parent-document semantic search.

        Thin async shell: stamp MCP activity, then hand the real work to a
        worker thread. The body is fully blocking (Ollama embed, ONNX
        rerank, SQLite reads), so running it inline stalls every other
        request for the duration — see ``_search_sync`` and issue #344.
        """
        if http_req.headers.get("X-Source") == "mcp":
            app.state.mcp_last_query = datetime.now(timezone.utc)
        try:
            return await run_in_threadpool(
                _search_sync,
                request,
                collection=collection,
                data_dir=data_dir,
                merged=_merged,
                get_spell_corrector=_get_spell_corrector,
                get_lexical_index=_get_lexical_index,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router

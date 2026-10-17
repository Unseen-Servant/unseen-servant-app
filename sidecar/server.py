"""
Unseen Servant sidecar — app construction and process lifecycle.

Started automatically by the Tauri desktop app. Builds one FastAPI app,
serves liveness and MCP connection state itself, and mounts each tool's
router (today: Legend Lore, ``legend_lore/router.py``).

Usage:
    python server.py --port 8420 --data-dir /path/to/app/data
"""

import argparse
import os
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from legend_lore.embedder import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    embed,
    embedder_status,
    start_background_tasks,
)
from legend_lore.library_store import LIBRARY_FILENAME, LibraryStore
from command.router import build_router as build_command_router
from legend_lore.router import build_router
from legend_lore.service import (
    load_manifest,
    remove_legacy_chroma,
    save_manifest,
    warm_search_stack,
)


# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------

PORT_FILENAME = "sidecar.port"


def parse_args():
    parser = argparse.ArgumentParser(description="Legend Lore indexing sidecar")
    parser.add_argument("--port", type=int, default=8420,
                        help="HTTP port; pass 0 to bind an ephemeral port")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Directory for the library store (default: ./chroma_db)")
    return parser.parse_args()


def write_port_file(data_dir: Path, port: int) -> None:
    """Atomically publish the bound port so Tauri/MCP can discover it.

    Written before uvicorn starts serving so the Rust readiness gate can
    pick it up the moment the process is alive. ``os.replace`` is atomic
    on POSIX and Windows so a partial read is not possible.
    """
    target = data_dir / PORT_FILENAME
    tmp = target.with_suffix(".port.tmp")
    tmp.write_text(str(port))
    os.replace(tmp, target)


def remove_port_file(data_dir: Path) -> None:
    """Best-effort cleanup of the published port file on shutdown."""
    try:
        (data_dir / PORT_FILENAME).unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def open_library_store(data_dir: Path) -> LibraryStore:
    """Open the production store, clearing what an older build left behind.

    Legacy Chroma files are deleted (the library is rebuilt, not migrated).
    A store opened under a different embedding model or dimension clears
    itself; every manifest entry is then marked outdated so sync reindexes
    it rather than trusting chunks that are no longer there.
    """
    freed = remove_legacy_chroma(data_dir)
    if freed:
        print(f"[store] removed legacy Chroma files: {freed:,} bytes")
    store = LibraryStore.open(
        data_dir / LIBRARY_FILENAME, EMBEDDING_MODEL, EMBEDDING_DIM
    )
    if store.was_reset:
        manifest = load_manifest(data_dir)
        for entry in manifest.files.values():
            entry.pipeline_version = ""
        save_manifest(data_dir, manifest)
    return store


def create_app(
    store: LibraryStore | None = None,
    data_dir: Path | None = None,
    embed_fn=None,
):
    """Create the FastAPI app, optionally with a pre-configured store.

    In production: called with no arguments — opens the library store in
    the ``--data-dir`` and embeds with Ollama.
    In tests: called with a store in a temp dir and a local embedder.

    Args:
        store: The library store (None = production auto-setup).
        data_dir: Directory for the store, manifest and settings.
                  In production, resolved from --data-dir CLI arg.
                  In tests, pass tmp_path.
        embed_fn: ``texts -> vectors``; defaults to ``embedder.embed``.
    """
    if store is None:
        args = parse_args()
        data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"
        data_dir.mkdir(parents=True, exist_ok=True)
        store = open_library_store(data_dir)
    if embed_fn is None:
        embed_fn = embed

    app = FastAPI(title="Legend Lore Sidecar")

    # Sidecar binds to 127.0.0.1 only, but the wildcard CORS still let any
    # local origin's webview talk to us. Tightening to the known Tauri
    # origins closes that off — production loads via tauri://localhost,
    # dev via http://localhost:1420 (per tauri.conf.json devUrl).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # MCP connection tracking — heartbeat + activity timestamps. Tracked
    # in-memory; any agent reconnect resends a heartbeat within 30s.
    app.state.mcp_last_heartbeat = None
    app.state.mcp_last_query = None

    # Warm-up progress, written by the ``warm_search_stack`` thread that
    # ``__main__`` starts. Plain strings under the GIL; nothing else writes.
    app.state.boot_steps = {"reranker": "pending", "spelling": "pending"}

    # ------------------------------------------------------------------
    # Workstation endpoints: liveness, boot progress and MCP connection state
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health():
        """Health check for startup detection."""
        return {"status": "ok"}

    @app.get("/api/boot")
    async def boot():
        """Warm-up progress, polled by the splash window until each step
        settles (``done``, ``failed`` or ``skipped``)."""
        return {"steps": app.state.boot_steps}

    @app.get("/api/models/status")
    def models_status():
        """Readiness of every ML model role the sidecar depends on.

        One row per role so the UI renders roles, not runtimes: a future
        reranker or chat-model row slots in without a frontend change.
        Sync ``def`` so the blocking probe runs in the threadpool.
        """
        return {"models": [embedder_status()]}

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

    # Legend Lore
    app.include_router(
        build_router(app, store, embed_fn, data_dir)
    )

    # Command
    app.include_router(build_command_router(app, data_dir))

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
    import asyncio
    import socket

    args = parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"

    # Install graceful-exit handlers BEFORE uvicorn does. uvicorn captures
    # signals during ``serve()`` and re-raises them after its own cleanup
    # (server.py:capture_signals); with Python's default SIGTERM handler
    # restored at that point, the process would be terminated before our
    # ``finally`` block runs and the port file would never be cleaned up.
    # Raising SystemExit instead lets the unwind reach the finally.
    def _graceful_exit(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, _graceful_exit)
    signal.signal(signal.SIGINT, _graceful_exit)

    # Pre-bind the socket ourselves so ``--port 0`` resolves to an actual port
    # number that we can publish to disk before uvicorn starts serving. The
    # Rust readiness gate polls ``data_dir/sidecar.port`` to learn where to
    # talk to us — without this, ephemeral binding would be opaque.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    actual_port = sock.getsockname()[1]
    print(f"Starting sidecar on port {actual_port}, data dir: {data_dir}")

    data_dir.mkdir(parents=True, exist_ok=True)
    write_port_file(data_dir, actual_port)

    # Start parent-death watchdog (daemon thread — won't block exit)
    parent_pid = os.getppid()
    watchdog = threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True)
    watchdog.start()

    # Backend-specific boot helpers (truncation probe, keep-warm ticker).
    start_background_tasks()

    application = create_app()

    # Same deal one layer up: the first search would otherwise load the
    # cross-encoder and build the spell vocabulary itself (issue #341).
    # Needs the app, so it starts here rather than beside the ticker.
    threading.Thread(
        target=warm_search_stack,
        args=(application.state.get_spell_corrector, application.state.boot_steps.__setitem__),
        daemon=True,
    ).start()

    config = uvicorn.Config(application, log_level="info")
    server = uvicorn.Server(config)
    try:
        asyncio.run(server.serve(sockets=[sock]))
    finally:
        remove_port_file(data_dir)

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

import chromadb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from legend_lore.router import build_router
from legend_lore.service import (
    COLLECTION_METADATA,
    build_embedding_function,
    gc_orphan_segments,
    keep_embedder_warm,
    probe_embed_truncation,
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
                        help="Directory for ChromaDB storage (default: ./chroma_db)")
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
        embedding_function = build_embedding_function()
        collection = chroma_client.get_or_create_collection(
            name="ttrpg_docs",
            embedding_function=embedding_function,
            metadata=COLLECTION_METADATA,
        )

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

    # ------------------------------------------------------------------
    # Workstation endpoints: liveness and MCP connection state
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

    # Legend Lore
    app.include_router(
        build_router(app, collection, data_dir, chroma_client, embedding_function)
    )

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

    # Truncation probe (daemon thread — diagnostics only, must not block
    # startup and must not fail it if Ollama isn't up yet)
    threading.Thread(target=probe_embed_truncation, daemon=True).start()

    # Keep bge-m3 resident so the first search after an idle spell doesn't
    # pay a cold model load (issue #341). Daemon thread, same contract.
    threading.Thread(target=keep_embedder_warm, daemon=True).start()

    application = create_app()

    # Same deal one layer up: the first search would otherwise load the
    # cross-encoder and build the spell vocabulary itself (issue #341).
    # Needs the app, so it starts here rather than beside the ticker.
    threading.Thread(
        target=warm_search_stack,
        args=(application.state.get_spell_corrector,),
        daemon=True,
    ).start()

    config = uvicorn.Config(application, log_level="info")
    server = uvicorn.Server(config)
    try:
        asyncio.run(server.serve(sockets=[sock]))
    finally:
        remove_port_file(data_dir)

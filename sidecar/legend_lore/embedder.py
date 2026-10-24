"""The embedding backend, behind one seam.

Everything that knows *how* text becomes a vector lives here: which
runtime serves the model, its name, and the identity string stamped
into every chunk and manifest entry. The rest of the sidecar sees a
callable ``texts -> vectors`` and a fingerprint.

bge-m3 runs on a ``llama-server`` this module starts and owns (#413): the
pinned llama.cpp build shipped beside the sidecar, the GGUF from the
shipped models, and flags set here, so nothing depends on how the user's
machine is set up. The sidecar's process group (Rust kills it on exit)
or process tree (Windows) takes the server with it.

``EMBEDDING_MODEL`` is that fingerprint. It feeds ``PIPELINE_VERSION``
(see ``chunker.py``), and ``preflight`` flags any manifest entry indexed
under a different value as outdated. So it must change whenever the
vectors would no longer be comparable — a different model, quantization,
or runtime that embeds differently — and must *not* change otherwise, or
every user's index is flagged for a needless re-index.
"""
from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from legend_lore import bundled

# Kept as the bare model name so indexes built before this module existed
# still match. The GGUF is the same file Ollama served before llama-server
# (sha256 daec91ff…), and its vectors match the stored ones within 1e-5
# (#413 step 1), so the runtime swap kept the name.
EMBEDDING_MODEL = "bge-m3"
# The library store fixes its vector table to this width and records it
# with EMBEDDING_MODEL; a store opened under different values clears
# itself, which is how a model change triggers the reindex.
EMBEDDING_DIM = 1024

# bge-m3 isn't causal: llama-server embeds an input in one physical batch
# (-ub) and rejects a longer one instead of truncating it, so the batch is
# the whole 8192-token context. Unified KV stops -np's slots from splitting
# that context four ways. Four slots serve the indexer's batches in flight
# (EMBED_CONCURRENCY) plus a search; eight added memory, not speed (#413).
MAX_INPUT_TOKENS = 8192
LLAMA_SERVER_FLAGS = (
    "--embeddings", "--pooling", "cls",
    "-c", "8192", "-b", "8192", "-ub", "8192",
    "--kv-unified", "-np", "4",
)
# Loading the 1.2 GB GGUF takes about a second warm, longer from a cold disk.
READY_TIMEOUT_SECONDS = 60.0

_REPO = Path(__file__).resolve().parents[2]

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_base_url: str | None = None
_log_dir: Path | None = None


def _embed_timeout() -> float:
    """Seconds to wait for one embed request.

    120s by default: chromadb's 60s was too tight for a 256-input bge-m3
    batch on slower hardware. Without an effective timeout, a wedged
    server blocks the worker thread indefinitely, which blocks
    ``fut.result()`` in ``_embed_and_upsert_units``, which holds the sync
    lock forever.

    Override at runtime with ``EMBED_TIMEOUT_SECONDS``.
    """
    return float(os.getenv("EMBED_TIMEOUT_SECONDS", "120"))


def _binary() -> Path | None:
    """The llama-server to run: ``LLAMA_SERVER_BIN`` (server.py sets it from
    ``--llama-server``), else, outside a build, the one
    ``scripts/build-llama-server.sh`` placed for ``tauri dev``."""
    if os.getenv("LLAMA_SERVER_BIN"):
        path = Path(os.environ["LLAMA_SERVER_BIN"])
    elif getattr(sys, "frozen", False):
        return None
    else:
        # Windows builds a folder, macOS a binary named for its triple.
        binaries = _REPO / "src-tauri" / "binaries"
        candidates = [binaries / "llama-server" / "llama-server.exe",
                      *sorted(binaries.glob("llama-server-*"))]
        path = next((p for p in candidates if p.is_file()), None)
    # build.rs leaves an empty placeholder until the script has run.
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return None
    return path


def _model() -> Path | None:
    """The bge-m3 GGUF: from ``BUNDLED_MODELS_DIR``, else, outside a build,
    the repo's ``models/`` (pytest and the evals)."""
    root = os.getenv("BUNDLED_MODELS_DIR")
    if not root and not getattr(sys, "frozen", False):
        root = str(_REPO / "models")
    folder = bundled.model_dir(root, "embed", EMBEDDING_MODEL)
    return next(iter(sorted(folder.glob("*.gguf"))), None) if folder else None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_embedder(log_dir: Path | None = None) -> None:
    """Start llama-server in the background, if it isn't running.

    server.py calls it at boot so the model loads behind the splash; an
    embed() that finds no server starts one too, which is how pytest and
    the evals get one. Never raises: a missing binary or model surfaces
    as the embed error and the status row.
    """
    global _proc, _base_url, _log_dir
    with _lock:
        if log_dir is not None:
            _log_dir = log_dir
        if _proc is not None and _proc.poll() is None:
            return
        binary, model = _binary(), _model()
        if binary is None or model is None:
            return
        port = _free_port()
        log = open(_log_dir / "llama-server.log", "w") if _log_dir else subprocess.DEVNULL
        try:
            _proc = subprocess.Popen(
                [str(binary), "-m", str(model), *LLAMA_SERVER_FLAGS,
                 "--host", "127.0.0.1", "--port", str(port)],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as e:
            print(f"Could not start llama-server ({binary}): {e}")
            return
        _base_url = f"http://127.0.0.1:{port}"


def stop_embedder() -> None:
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _proc.kill()
        _proc = None


atexit.register(stop_embedder)


def _ready() -> str:
    """The base URL of a llama-server that has its model loaded.

    Starts or restarts the server when it isn't running (a crash mid-index
    comes back on the next batch's retry), then waits for ``/health``.
    """
    import httpx

    start_embedder()
    if _proc is None or _base_url is None:
        missing = "llama-server" if _binary() is None else f"the {EMBEDDING_MODEL} model"
        raise RuntimeError(
            f"Embedder not available — {missing} is missing from the app. "
            "Reinstall Unseen Servant."
        )
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while True:
        if _proc.poll() is not None:
            raise RuntimeError(
                f"Embedder stopped (exit code {_proc.returncode}). "
                "Try again; if it keeps stopping, see llama-server.log."
            )
        try:
            if httpx.get(f"{_base_url}/health", timeout=2.0).status_code == 200:
                return _base_url
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"Embedder not answering — not ready after {READY_TIMEOUT_SECONDS:.0f}s. "
                "Try again in a moment."
            )
        time.sleep(0.2)


def _fit(base: str, texts: list[str]) -> list[str]:
    """``texts`` with any input over the server's batch cut to fit.

    Today's library peaks at 1,888 tokens, but the chunker's HARD_CAP
    allows more, and llama-server rejects an over-long input where Ollama
    used to cut it. Cutting keeps that old behaviour for the rare unit.
    """
    import httpx

    fitted = []
    for text in texts:
        toks = httpx.post(f"{base}/tokenize", json={"content": text}, timeout=30).json()["tokens"]
        with_specials = httpx.post(
            f"{base}/tokenize", json={"content": text, "add_special": True}, timeout=30,
        ).json()["tokens"]
        keep = MAX_INPUT_TOKENS - (len(with_specials) - len(toks))
        if len(toks) > keep:
            text = httpx.post(
                f"{base}/detokenize", json={"tokens": toks[:keep]}, timeout=30,
            ).json()["content"]
        fitted.append(text)
    return fitted


def embed(texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` with bge-m3 — one request, vectors in input order.

    OpenAI-dialect ``/v1/embeddings``; llama-server returns normalised
    vectors, as Ollama's ``/api/embed`` did. Raises on a non-200 answer
    with the server's own message, and on no answer with a plain one.
    """
    import httpx

    base = _ready()
    timeout = _embed_timeout()
    texts = list(texts)
    # The raw httpx errors ("[Errno 61] Connection refused") reach the
    # search error, Claude via MCP, and a sync's per-book errors verbatim;
    # say what they mean in the status bar's own terms instead.
    for attempt in (1, 2):
        try:
            resp = httpx.post(
                f"{base}/v1/embeddings",
                json={"model": EMBEDDING_MODEL, "input": texts},
                timeout=timeout,
            )
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Embedder not running — nothing answered at {base}. "
                "Try again in a moment."
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError(
                f"Embedder not answering — no reply after {timeout:.0f}s. "
                "It may be busy or stuck; try again in a moment."
            ) from e
        if resp.status_code == 200:
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        try:
            detail = resp.json().get("error", resp.text)
            if isinstance(detail, dict):
                detail = detail.get("message", detail)
        except ValueError:
            detail = resp.text
        if attempt == 1 and "too large" in str(detail):
            texts = _fit(base, texts)
            continue
        raise RuntimeError(f"embed failed ({resp.status_code}): {detail}")


def embedder_status() -> dict:
    """Readiness of the embedding backend, for the desktop UI.

    ``runtime_up`` is whether llama-server is running; ``ready`` is
    whether it has also loaded the model and answers. Never raises — a
    down runtime is a status, not an error.
    """
    import httpx

    runtime_up = _proc is not None and _proc.poll() is None
    ready = False
    if runtime_up:
        try:
            ready = httpx.get(f"{_base_url}/health", timeout=3.0).status_code == 200
        except Exception:
            pass
    return {
        "role": "embed",
        "runtime": "llama-server",
        "model": EMBEDDING_MODEL,
        "runtime_up": runtime_up,
        "ready": ready,
    }

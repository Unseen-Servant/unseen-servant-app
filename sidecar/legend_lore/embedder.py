"""The embedding backend, behind one seam.

Everything that knows *how* text becomes a vector lives here: which
runtime serves the model, its name, and the identity string stamped
into every chunk and manifest entry. Swapping the runtime (e.g. Ollama
→ a bundled llama-server) means changing this file only; the rest of the
sidecar sees a callable ``texts -> vectors`` and a fingerprint.

``EMBEDDING_MODEL`` is that fingerprint. It feeds ``PIPELINE_VERSION``
(see ``chunker.py``), and ``preflight`` flags any manifest entry indexed
under a different value as outdated. So it must change whenever the
vectors would no longer be comparable — a different model, quantization,
or runtime that embeds differently — and must *not* change otherwise, or
every user's index is flagged for a needless re-index.
"""
from __future__ import annotations

import os
import threading

# Kept as the bare model name (not ``ollama/bge-m3``) so indexes built
# before this module existed still match. Extend the string when the
# backend changes, e.g. ``bge-m3/llamacpp-q8``.
EMBEDDING_MODEL = "bge-m3"
EMBED_BASE_URL = "http://localhost:11434"

# NOTE for the runtime swap: Chroma persists the embedding function's
# ``name()`` ("ollama") in the collection config and refuses to open the
# collection if a differently named function is supplied. A new backend
# therefore needs a boot-time drop-and-recreate of the collection when
# the persisted name differs, not just the fingerprint bump.


def build_embedding_function():
    """Construct the embedding function for the configured backend.

    Currently Ollama serving bge-m3 on its default port, with an explicit
    timeout: chromadb defaults to 60s, which is too tight for a 256-input
    bge-m3 batch on slower hardware. Without an effective timeout, a
    wedged Ollama (process suspended, network down) blocks the worker
    thread indefinitely, which blocks ``fut.result()`` in
    ``_embed_and_upsert_units``, which holds the sync lock forever.

    Override at runtime with ``OLLAMA_EMBED_TIMEOUT_SECONDS``.
    """
    from chromadb.utils import embedding_functions

    timeout = int(os.getenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "120"))
    return embedding_functions.OllamaEmbeddingFunction(
        url=EMBED_BASE_URL,
        model_name=EMBEDDING_MODEL,
        timeout=timeout,
    )


def embedder_status() -> dict:
    """Readiness of the embedding backend, for the desktop UI.

    ``runtime_up`` is whether the serving process answers at all;
    ``ready`` is whether it also has the model. Two flags rather than one
    because the UI's remedy differs: install/launch the runtime vs. pull
    the model. Never raises — a down runtime is a status, not an error.
    """
    import httpx

    # OpenAI-dialect ``/v1/models`` rather than Ollama's ``/api/tags``:
    # llama-server, LM Studio and vLLM answer the same shape, so a runtime
    # swap changes the base URL, not the probe.
    runtime_up = ready = False
    try:
        resp = httpx.get(f"{EMBED_BASE_URL}/v1/models", timeout=3.0)
        if resp.status_code == 200:
            runtime_up = True
            models = resp.json().get("data", [])
            ready = any(
                m.get("id", "").startswith(EMBEDDING_MODEL) for m in models
            )
    except Exception:
        pass
    return {
        "role": "embed",
        "runtime": "ollama",
        "model": EMBEDDING_MODEL,
        "runtime_up": runtime_up,
        "ready": ready,
    }


def probe_embed_truncation(embed_fn=None) -> None:
    """Warn when the effective Ollama embed context silently truncates.

    Embeds a ~8k-token filler text and the same text with a distinctive
    sentinel tail; identical vectors mean the tail was cut off — i.e.
    the Ollama server is running below bge-m3's native 8192 context
    (measured ~2048 on a dev machine when OLLAMA_CONTEXT_LENGTH was not
    set for the server process). Diagnostics only: prints a warning and
    never raises; indexing and search do not depend on it.
    """
    try:
        if embed_fn is None:
            embed_fn = build_embedding_function()
        base = "word " * 8000  # ~8k bge-m3 tokens, inside the native window
        tail = "zanzibar quetzal umbra"
        vec_a = list(embed_fn([base])[0])
        vec_b = list(embed_fn([base + tail])[0])
        if vec_a == vec_b:
            print(
                "WARNING: Ollama embed truncation detected — a sentinel tail "
                "at ~8k tokens did not change the embedding. The effective "
                "context is below bge-m3's native 8192, so long sections are "
                "only partially searchable. Set OLLAMA_CONTEXT_LENGTH=8192 "
                "for the Ollama server process and re-index."
            )
    except Exception as e:
        print(f"Embed truncation probe skipped: {e}")


# Ollama unloads an idle model after ~5 minutes, so the first search after
# a lull pays a full bge-m3 load — several seconds, and (before #344) on the
# event loop. Re-embedding a single token well inside that window resets the
# idle timer for a few milliseconds of work. Issue #341.
EMBED_KEEPALIVE_INTERVAL_SECONDS = float(
    os.getenv("OLLAMA_KEEPALIVE_INTERVAL_SECONDS", "120")
)


def keep_embedder_warm(
    embed_fn=None,
    interval: float | None = None,
    stop: threading.Event | None = None,
) -> None:
    """Background thread: keep bge-m3 resident by embedding periodically.

    Diagnostics-grade error handling, like ``probe_embed_truncation``: a
    down or wedged Ollama must never take the sidecar with it, and a failed
    tick is not worth reporting — the next search will surface the problem
    with far better context. Set ``OLLAMA_KEEPALIVE_INTERVAL_SECONDS=0`` to
    disable.
    """
    interval = EMBED_KEEPALIVE_INTERVAL_SECONDS if interval is None else interval
    if interval <= 0:
        return
    stop = stop or threading.Event()
    if embed_fn is None:
        try:
            embed_fn = build_embedding_function()
        except Exception:
            return
    while not stop.wait(interval):
        try:
            embed_fn(["ping"])
        except Exception:
            pass


def start_background_tasks() -> None:
    """Start the boot-time helpers this backend needs, as daemon threads.

    Both are Ollama-shaped: the truncation probe checks a server-side
    context setting we don't control, and the keep-warm ticker works
    around Ollama's idle unload. A bundled runtime would need neither, so
    the decision lives here rather than in server.py. Neither may block
    startup or fail it if the runtime isn't up yet.
    """
    threading.Thread(target=probe_embed_truncation, daemon=True).start()
    threading.Thread(target=keep_embedder_warm, daemon=True).start()

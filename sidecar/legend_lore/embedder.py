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

# Kept as the bare model name (not ``ollama/bge-m3``) so indexes built
# before this module existed still match. Extend the string when the
# backend changes, e.g. ``bge-m3/llamacpp-q8``.
EMBEDDING_MODEL = "bge-m3"


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
        url="http://localhost:11434/api/embeddings",
        model_name=EMBEDDING_MODEL,
        timeout=timeout,
    )

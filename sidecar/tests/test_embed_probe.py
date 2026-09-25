"""Startup embed-truncation probe: warn when Ollama's effective context
silently truncates long inputs (#327 — measured ~2048 on a dev machine
vs bge-m3's native 8192)."""

from legend_lore.service import probe_embed_truncation


def test_probe_warns_when_tail_truncated(capsys):
    """An embedder that ignores the tail returns identical vectors for
    base and base+sentinel — the probe must warn."""
    def truncating_embed(texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    probe_embed_truncation(embed_fn=truncating_embed)
    out = capsys.readouterr().out
    assert "truncation detected" in out
    assert "OLLAMA_CONTEXT_LENGTH" in out


def test_probe_silent_when_context_full(capsys):
    """Vectors that differ mean the tail was seen — no warning."""
    def full_embed(texts):
        return [[float(len(t) % 97), 0.5] for t in texts]

    probe_embed_truncation(embed_fn=full_embed)
    assert "truncation detected" not in capsys.readouterr().out


def test_probe_swallows_embedder_errors(capsys):
    """Search must not depend on the probe: an unreachable Ollama is a
    debug-level skip, never a raise."""
    def broken_embed(texts):
        raise RuntimeError("connection refused")

    probe_embed_truncation(embed_fn=broken_embed)  # must not raise
    assert "probe skipped" in capsys.readouterr().out

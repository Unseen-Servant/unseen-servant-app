"""Keep bge-m3 resident between searches (#341).

Ollama unloads an idle model after ~5 minutes, so the first search after a
lull pays a full model load. The keep-warm ticker re-embeds one token well
inside that window. Same contract as the truncation probe: an injectable
embedder, and failures that never escape.
"""

import threading

from legend_lore import service
from legend_lore.embedder import (
    EMBED_KEEPALIVE_INTERVAL_SECONDS,
    keep_embedder_warm,
)
from legend_lore.service import warm_search_stack


def test_ticker_embeds_on_each_interval():
    """Each tick embeds something small, until stopped."""
    calls = []
    stop = threading.Event()

    def embed(texts):
        calls.append(texts)
        if len(calls) >= 3:
            stop.set()
        return [[0.0] for _ in texts]

    keep_embedder_warm(embed_fn=embed, interval=0.01, stop=stop)

    assert len(calls) == 3
    # One short input per tick — the point is to reset the idle timer, not
    # to do work.
    assert all(len(t) == 1 for t in calls)


def test_ticker_survives_a_down_ollama():
    """A wedged or absent Ollama must not kill the thread or the sidecar."""
    calls = []
    stop = threading.Event()

    def broken(texts):
        calls.append(texts)
        if len(calls) >= 3:
            stop.set()
        raise RuntimeError("connection refused")

    keep_embedder_warm(embed_fn=broken, interval=0.01, stop=stop)  # must not raise

    # Kept ticking through the failures rather than giving up on the first.
    assert len(calls) == 3


def test_ticker_disabled_by_zero_interval():
    """The escape hatch for anyone who doesn't want the background traffic."""
    calls = []

    def embed(texts):
        calls.append(texts)
        return [[0.0] for _ in texts]

    keep_embedder_warm(embed_fn=embed, interval=0)

    assert calls == []


def test_ticker_waits_before_the_first_embed():
    """The ticker must not fire immediately — startup already embeds via
    the truncation probe, and a burst at boot helps nobody."""
    stop = threading.Event()
    stop.set()  # pre-stopped: the first wait() returns True at once

    calls = []
    keep_embedder_warm(embed_fn=lambda t: calls.append(t), interval=60, stop=stop)

    assert calls == []


# ---------------------------------------------------------------------------
# Boot warm-up (#341): pay the lazy loads before the first search does
# ---------------------------------------------------------------------------

def test_keepalive_default_interval_is_120s():
    """Ollama unloads an idle model after ~5 minutes; 240 s left no margin
    for a slow or skipped tick."""
    assert EMBED_KEEPALIVE_INTERVAL_SECONDS == 120.0


def test_warm_search_stack_loads_reranker_and_vocabulary(monkeypatch):
    monkeypatch.delenv("RERANK_DISABLED", raising=False)
    reranked = []
    monkeypatch.setattr(service, "rerank_scores",
        lambda query, docs: reranked.append((query, docs)) or [0.0])
    built = []

    warm_search_stack(lambda: built.append(1))

    assert reranked == [("warm", ["warm"])]
    assert built == [1]


def test_warm_search_stack_skips_the_reranker_when_disabled(monkeypatch):
    """RERANK_DISABLED means the model is never loaded — warming it would
    only burn a thread on a load that is going to be refused."""
    monkeypatch.setenv("RERANK_DISABLED", "1")
    reranked = []
    monkeypatch.setattr(service, "rerank_scores", lambda query, docs: reranked.append(1))
    built = []

    warm_search_stack(lambda: built.append(1))

    assert reranked == []
    assert built == [1]  # the vocabulary is still worth warming


def test_warm_search_stack_survives_a_failing_reranker(monkeypatch):
    """Same diagnostics-grade contract as the keepalive ticker: a warm-up
    failure must never take the sidecar down at boot."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)

    def boom(query, docs):
        raise RuntimeError("no model")

    monkeypatch.setattr(service, "rerank_scores", boom)
    built = []

    warm_search_stack(lambda: built.append(1))  # must not raise

    assert built == [1]

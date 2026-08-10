"""Keep bge-m3 resident between searches (#341).

Ollama unloads an idle model after ~5 minutes, so the first search after a
lull pays a full model load. The keep-warm ticker re-embeds one token well
inside that window. Same contract as the truncation probe: an injectable
embedder, and failures that never escape.
"""

import threading

from server import keep_embedder_warm


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

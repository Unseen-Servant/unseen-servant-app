"""
Tests for the concurrent embed helper (issue #158).

The thread-pool fans out embeds, but vectors must be collected in
submission order so they stay aligned with the embed units the store
writes them against. These tests force out-of-order embed completion and
assert the collected vectors are still in submission order.
"""

import time
from pathlib import Path

from legend_lore.granularity import EmbedUnit
from legend_lore.service import _embed_units


def _delayed_embed(embed_delay):
    """Embedder whose latency depends on the batch's first ordinal; each
    vector carries its own unit's ordinal so order can be checked."""

    def embed(texts):
        # Each text is "text <ordinal>"; first ordinal pins the batch index.
        time.sleep(embed_delay(int(texts[0].split()[1])))
        return [[float(t.split()[1])] * 4 for t in texts]

    return embed


def _make_units(n: int) -> list[EmbedUnit]:
    return [
        EmbedUnit(
            chunk_id=str(i),
            text=f"text {i}",
            parent_id=f"p_{i // 3}",
            chunk_type="prose",
            section_heading=None,
            source_pdf="test.pdf",
            page_start=1,
            page_end=1,
            ordinal=i,
        )
        for i in range(n)
    ]


def test_vector_order_is_deterministic_under_out_of_order_embed_completion():
    """Earlier batches that embed slowly must still be collected first.

    Inverts the natural latency: later batches return faster than earlier
    ones, so a naive `as_completed` drain would collect them out of order
    and pair vectors with the wrong units.
    """
    units = _make_units(30)  # 10 batches at batch_size=3

    # First batch (ordinal 0) sleeps the longest; last batch (ordinal 27)
    # returns almost instantly. Forces out-of-order completion.
    embed = _delayed_embed(lambda o: max(0, (30 - o) * 0.005))

    vectors: list[list[float]] = []
    list(_embed_units(
        embed, units, Path("test.pdf"), vectors, batch_size=3, concurrency=4,
    ))

    flat = [int(v[0]) for v in vectors]
    assert flat == list(range(30)), (
        f"Expected vector ordinals to be monotonic 0..29, got: {flat}"
    )


def test_yields_per_batch_unit_counts_in_order():
    """The generator should yield one int per batch, summing to total units."""
    units = _make_units(7)  # batch_size=3 -> [3, 3, 1]
    vectors: list[list[float]] = []

    yields = list(_embed_units(
        _delayed_embed(lambda _o: 0.0), units, Path("test.pdf"), vectors,
        batch_size=3, concurrency=2,
    ))

    assert yields == [3, 3, 1]
    assert sum(yields) == len(units) == len(vectors)


def test_empty_input_yields_nothing():
    vectors: list[list[float]] = []
    assert list(_embed_units(
        _delayed_embed(lambda _o: 0.0), [], Path("test.pdf"), vectors,
    )) == []
    assert vectors == []

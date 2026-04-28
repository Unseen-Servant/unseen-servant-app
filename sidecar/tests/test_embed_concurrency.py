"""
Tests for the concurrent embed -> serial upsert helper (issue #158).

The thread-pool fans out embeds, but upserts must commit in submission
order so chunk ordinals stay monotonic in Chroma. These tests force
out-of-order embed completion and assert the upsert sequence is still
in submission order.
"""

import time
from pathlib import Path

from granularity import EmbedUnit
from server import _embed_and_upsert_units


class _FakeCollection:
    """Minimal stand-in: sync embedding function + upsert recorder."""

    def __init__(self, embed_delay):
        self._embedding_function = self._embed
        self._embed_delay = embed_delay
        self.upsert_calls = []  # list of id lists, in commit order

    def _embed(self, texts):
        # Each text is "text <ordinal>"; first ordinal pins the batch index.
        first_ordinal = int(texts[0].split()[1])
        time.sleep(self._embed_delay(first_ordinal))
        return [[float(first_ordinal)] * 4 for _ in texts]

    def upsert(self, *, embeddings, documents, metadatas, ids):
        self.upsert_calls.append(list(ids))


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


def test_upsert_order_is_deterministic_under_out_of_order_embed_completion():
    """Earlier batches that embed slowly must still be upserted first.

    Inverts the natural latency: later batches return faster than earlier
    ones, so a naive `as_completed` drain would commit them out of order
    and corrupt the on-disk chunk sequence.
    """
    units = _make_units(30)  # 10 batches at batch_size=3

    # First batch (ordinal 0) sleeps the longest; last batch (ordinal 27)
    # returns almost instantly. Forces out-of-order completion.
    coll = _FakeCollection(embed_delay=lambda o: max(0, (30 - o) * 0.005))

    list(_embed_and_upsert_units(
        coll, units, Path("test.pdf"), "unknown", "stem",
        batch_size=3, concurrency=4,
    ))

    flat = [int(cid.rsplit("_", 1)[1]) for ids in coll.upsert_calls for cid in ids]
    assert flat == list(range(30)), (
        f"Expected upsert ordinals to be monotonic 0..29, got: {flat}"
    )


def test_yields_per_batch_unit_counts_in_order():
    """The generator should yield one int per batch, summing to total units."""
    units = _make_units(7)  # batch_size=3 -> [3, 3, 1]
    coll = _FakeCollection(embed_delay=lambda _o: 0.0)

    yields = list(_embed_and_upsert_units(
        coll, units, Path("test.pdf"), "unknown", "stem",
        batch_size=3, concurrency=2,
    ))

    assert yields == [3, 3, 1]
    assert sum(yields) == len(units)


def test_empty_input_yields_nothing():
    coll = _FakeCollection(embed_delay=lambda _o: 0.0)
    assert list(_embed_and_upsert_units(
        coll, [], Path("test.pdf"), "unknown", "stem",
    )) == []
    assert coll.upsert_calls == []

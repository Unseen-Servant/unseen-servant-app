"""
Tests for the embed batch runner.

The indexer hands the embedder one batch at a time: llama-server takes
inputs first come, first served, so everything in flight is what a
search's query waits behind (EMBED_BATCH_SIZE in service.py). Vectors come
back in unit order, one progress count per batch.
"""

import threading
import time
from pathlib import Path

from legend_lore.granularity import EmbedUnit
from legend_lore.service import EMBED_BATCH_SIZE, _embed_units


def _embed(texts):
    """Each text is "text <ordinal>"; its vector carries the ordinal."""
    return [[float(t.split()[1])] * 4 for t in texts]


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


def test_one_batch_is_with_the_embedder_at_a_time():
    """A second batch in flight is a second batch a search waits behind."""
    in_flight = 0
    most = 0
    lock = threading.Lock()

    def embed(texts):
        nonlocal in_flight, most
        with lock:
            in_flight += 1
            most = max(most, in_flight)
        time.sleep(0.01)
        with lock:
            in_flight -= 1
        return _embed(texts)

    vectors: list[list[float]] = []
    list(_embed_units(embed, _make_units(30), Path("test.pdf"), vectors, batch_size=3))

    assert most == 1
    assert [int(v[0]) for v in vectors] == list(range(30))


def test_a_batch_is_small_enough_for_a_search_to_get_its_turn():
    """The default is what a sync runs with. 256 units, three batches at a
    time, kept a search waiting 13 to 20 s on an M1 Pro; 32 keeps it under
    a second."""
    sizes = []

    def embed(texts):
        sizes.append(len(texts))
        return _embed(texts)

    list(_embed_units(embed, _make_units(100), Path("test.pdf"), []))

    assert EMBED_BATCH_SIZE <= 64
    assert sizes == [EMBED_BATCH_SIZE] * (100 // EMBED_BATCH_SIZE) + [100 % EMBED_BATCH_SIZE]


def test_a_caller_that_stops_reading_stops_the_embedding():
    """A sync that is abandoned mustn't embed the rest of the book while
    it holds the sync lock."""
    embedded = []

    def embed(texts):
        embedded.append(len(texts))
        return _embed(texts)

    progress = _embed_units(embed, _make_units(30), Path("test.pdf"), [], batch_size=3)
    next(progress)
    progress.close()

    assert embedded == [3]


def test_yields_per_batch_unit_counts_in_order():
    """The generator should yield one int per batch, summing to total units."""
    units = _make_units(7)  # batch_size=3 -> [3, 3, 1]
    vectors: list[list[float]] = []

    yields = list(_embed_units(_embed, units, Path("test.pdf"), vectors, batch_size=3))

    assert yields == [3, 3, 1]
    assert sum(yields) == len(units) == len(vectors)


def test_empty_input_yields_nothing():
    vectors: list[list[float]] = []
    assert list(_embed_units(_embed, [], Path("test.pdf"), vectors)) == []
    assert vectors == []

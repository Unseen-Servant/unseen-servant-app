"""Tests for search not monopolising the event loop (issue #344).

``/api/search`` is declared ``async def`` but its body is entirely
synchronous — Chroma's query (which embeds via a *blocking* HTTP call to
Ollama), the cross-encoder rerank, and several manifest reads all run
inline. Every millisecond of that runs on the uvicorn event loop, so one
5-7s search stalls every other request: health polls, MCP heartbeats, and
(once it exists) the Unseen Servant's token stream.

The fix is to run the body in a threadpool. These tests pin the property
rather than the implementation: a search in flight must not stop the
server answering something else.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from server import create_app

# How long the fake query holds the gate if the test fails to release it.
# Bounds the damage when the event loop *is* blocked: the test fails by
# timeout instead of hanging the suite.
GATE_TIMEOUT = 3.0


@pytest.fixture
def app(test_collection, test_chroma_client, test_embedding_function, tmp_path):
    return create_app(
        collection=test_collection,
        data_dir=tmp_path,
        chroma_client=test_chroma_client,
        embedding_function=test_embedding_function,
    )


async def test_search_does_not_block_the_event_loop(app, test_collection, monkeypatch):
    """While a search is mid-flight, /health must still answer.

    The property has to be encoded as *ordering*, not as a timeout: a
    blocked event loop cannot run the very assertions that would observe
    it, so anything awaited from this coroutine only resolves once the
    block has already lifted.

    So the dependency is inverted. The fake query parks until /health has
    completed, and /health can only complete if the loop is free:

    - threadpooled (fixed): query runs on a worker, the loop serves
      /health, the event fires, the query returns at once.
    - inline (broken):      the query owns the loop, /health can never be
      served, and the query only unparks on its own timeout.

    Elapsed time therefore separates the two cases cleanly.
    """
    served_health = threading.Event()
    entered_query = threading.Event()

    def blocking_query(*args, **kwargs):
        entered_query.set()
        served_health.wait(timeout=GATE_TIMEOUT)
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    monkeypatch.setattr(test_collection, "query", blocking_query)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        loop = asyncio.get_running_loop()
        started = loop.time()

        search = asyncio.create_task(
            c.post("/api/search", json={"query": "anything", "n_results": 3})
        )
        health = asyncio.create_task(c.get("/health"))
        health.add_done_callback(lambda _: served_health.set())

        search_res, health_res = await asyncio.gather(search, health)
        elapsed = loop.time() - started

    assert entered_query.is_set(), "search never reached the query call"
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"
    assert search_res.status_code == 200
    assert elapsed < GATE_TIMEOUT / 2, (
        f"/health was not served for {elapsed:.2f}s while a search was in "
        f"flight — the search handler is blocking the event loop (#344)"
    )


async def test_concurrent_searches_both_succeed(app, test_collection):
    """Two searches in flight at once must both return correct results.

    Guards the premise the threadpool move rests on: Chroma collection
    reads are safe from multiple threads.
    """
    test_collection.add(
        ids=["a", "b"],
        documents=[
            "The fire drake breathes gouts of flame and hoards gold.",
            "Rope, hempen, 50 feet. Costs 1 gp and weighs 10 pounds.",
        ],
        metadatas=[
            {"filename": "bestiary.pdf", "source": "/lib/bestiary.pdf",
             "parent_id": "p1", "section_heading": "Fire Drake",
             "page_start": 1, "page_end": 1, "game_system": "unknown"},
            {"filename": "gear.pdf", "source": "/lib/gear.pdf",
             "parent_id": "p2", "section_heading": "Rope",
             "page_start": 2, "page_end": 2, "game_system": "unknown"},
        ],
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        drake, rope = await asyncio.gather(
            c.post("/api/search", json={"query": "fire breathing dragon", "n_results": 2}),
            c.post("/api/search", json={"query": "climbing rope cost", "n_results": 2}),
        )

    assert drake.status_code == 200 and rope.status_code == 200
    assert drake.json()["results"][0]["filename"] == "bestiary.pdf"
    assert rope.json()["results"][0]["filename"] == "gear.pdf"


def test_collection_query_is_thread_safe(test_collection):
    """Direct-to-Chroma concurrency check, independent of FastAPI.

    If this fails, the threadpool approach is unsound and the fix has to
    serialise instead — so it's worth pinning separately from the routes.
    """
    test_collection.add(
        ids=[f"c{i}" for i in range(20)],
        documents=[f"Chunk number {i} about dragons and dungeons." for i in range(20)],
        metadatas=[{"parent_id": f"p{i}"} for i in range(20)],
    )

    def query(n):
        return test_collection.query(query_texts=[f"dragons {n}"], n_results=5)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(query, range(16)))

    assert len(results) == 16
    for r in results:
        assert len(r["documents"][0]) == 5

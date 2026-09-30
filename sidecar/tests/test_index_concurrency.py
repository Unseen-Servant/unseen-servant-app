"""
Regression tests for /api/index-files and /api/reindex-file event-loop blocking.

If these endpoints are declared as ``async def`` while their bodies do heavy
synchronous work (PyMuPDF + Ollama + SQLite), the FastAPI event loop is blocked
for the entire indexing duration. Real-world consequence: the frontend's
``/health`` poll times out, the sidecar appears disconnected, and the user-
facing "Add to index" / "Re-index" right-click actions look broken.

The fix is to declare the endpoints as plain ``def`` so FastAPI runs them in
a worker thread, leaving the event loop free. The tests pin that as an
ordering (the indexer waits for /health) rather than a wall-clock bound.
"""

import asyncio
import threading

import httpx
import pytest
from httpx import ASGITransport

import server
from legend_lore import router

# How long the fake indexer waits for /health before giving up. Only a
# blocked event loop ever reaches it; a passing run is released at once.
GATE_TIMEOUT = 10.0


@pytest.fixture
def gate():
    return {"entered": threading.Event(), "health_served": threading.Event(), "released": None}


@pytest.fixture
def gated_app(monkeypatch, gate, test_store, test_embed_fn, tmp_path):
    """App whose index_single_pdf parks until /health has been served.

    It records whether /health released it (True) or it gave up waiting
    (False) — which only happens when the endpoint runs on the event loop,
    so /health can't be served until it returns.
    """

    def gated_index(pdf_path, store, embed_fn, **kwargs):
        gate["entered"].set()
        gate["released"] = gate["health_served"].wait(timeout=GATE_TIMEOUT)
        return 1, None, "unknown", []

    monkeypatch.setattr(router, "index_single_pdf", gated_index)
    return server.create_app(store=test_store, data_dir=tmp_path, embed_fn=test_embed_fn)


@pytest.fixture
def dummy_pdf(tmp_path):
    """A real file on disk so reindex_file's existence check passes."""
    p = tmp_path / "dummy.pdf"
    p.write_bytes(b"%PDF-1.4\n%EOF\n")
    return p


async def _health_during(app, gate, slow_call):
    """Start ``slow_call``; once its indexer is running, request /health.

    Ordering, not timing: /health is only requested after the indexer has
    entered, so on a blocked loop it cannot be served until the indexer
    has already given up. Returns (health_response, slow_response).
    """
    loop = asyncio.get_running_loop()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        slow = asyncio.create_task(slow_call(ac))
        entered = await loop.run_in_executor(None, gate["entered"].wait, GATE_TIMEOUT)
        assert entered, "the endpoint never reached index_single_pdf"
        health = await ac.get("/health")
        gate["health_served"].set()
        return health, await slow


async def test_index_files_does_not_block_event_loop(gated_app, gate, dummy_pdf):
    """/health must respond during a slow /api/index-files call."""

    async def kick_index(ac):
        return await ac.post("/api/index-files", json={"paths": [str(dummy_pdf)]}, timeout=30.0)

    health, index_resp = await _health_during(gated_app, gate, kick_index)

    assert health.status_code == 200
    assert index_resp.status_code == 200
    assert gate["released"] is True, (
        "/api/index-files held the event loop: /health was only served after "
        "indexing gave up waiting for it."
    )


async def test_reindex_file_does_not_block_event_loop(gated_app, gate, dummy_pdf):
    """/health must respond during a slow /api/reindex-file call."""

    async def kick_reindex(ac):
        return await ac.post("/api/reindex-file", json={"path": str(dummy_pdf)}, timeout=30.0)

    health, reindex_resp = await _health_during(gated_app, gate, kick_reindex)

    assert health.status_code == 200
    assert reindex_resp.status_code == 200
    assert gate["released"] is True, (
        "/api/reindex-file held the event loop: /health was only served after "
        "indexing gave up waiting for it."
    )

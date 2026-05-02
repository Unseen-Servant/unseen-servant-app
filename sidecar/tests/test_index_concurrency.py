"""
Regression tests for /api/index-files and /api/reindex-file event-loop blocking.

If these endpoints are declared as ``async def`` while their bodies do heavy
synchronous work (PyMuPDF + Ollama + Chroma), the FastAPI event loop is blocked
for the entire indexing duration. Real-world consequence: the frontend's
``/health`` poll times out, the sidecar appears disconnected, and the user-
facing "Add to index" / "Re-index" right-click actions look broken.

The fix is to declare the endpoints as plain ``def`` so FastAPI runs them in
a worker thread, leaving the event loop free.
"""

import asyncio
import time

import httpx
import pytest
from httpx import ASGITransport

import server


SLOW_S = 1.5
HEALTH_DELAY_S = 0.2


@pytest.fixture
def slow_app(
    monkeypatch, test_collection, test_chroma_client, test_embedding_function, tmp_path
):
    """App where index_single_pdf sleeps for SLOW_S to simulate a real PDF."""

    def slow_index(pdf_path, collection, **kwargs):
        time.sleep(SLOW_S)
        return 1, None, "unknown", []

    monkeypatch.setattr(server, "index_single_pdf", slow_index)

    app = server.create_app(
        collection=test_collection,
        data_dir=tmp_path,
        chroma_client=test_chroma_client,
        embedding_function=test_embedding_function,
    )
    return app


@pytest.fixture
def dummy_pdf(tmp_path):
    """A real file on disk so reindex_file's existence check passes."""
    p = tmp_path / "dummy.pdf"
    p.write_bytes(b"%PDF-1.4\n%EOF\n")
    return p


async def _measure_health_during(app, slow_call):
    """Fire ``slow_call`` and a /health request concurrently.

    Returns (health_response, when_health_returned_s, slow_response).

    ``when_health_returned_s`` is wall time from the start of the gather to
    when /health returned. If the event loop is blocked by the slow call,
    /health can't return until the slow call finishes, so the value will be
    >= SLOW_S. If the loop stays responsive, /health returns close to
    HEALTH_DELAY_S after a small initial delay.
    """
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        t_start = time.perf_counter()

        async def health_after_delay():
            await asyncio.sleep(HEALTH_DELAY_S)
            response = await ac.get("/health")
            return response, time.perf_counter() - t_start

        slow_resp, (health_resp, when_returned) = await asyncio.gather(
            slow_call(ac),
            health_after_delay(),
        )
        return health_resp, when_returned, slow_resp


@pytest.mark.asyncio
async def test_index_files_does_not_block_event_loop(slow_app, dummy_pdf):
    """/health must respond during a slow /api/index-files call."""

    async def kick_index(ac):
        return await ac.post(
            "/api/index-files",
            json={"paths": [str(dummy_pdf)]},
            timeout=10.0,
        )

    health, when_returned, index_resp = await _measure_health_during(slow_app, kick_index)

    assert health.status_code == 200
    assert index_resp.status_code == 200
    # /health must come back well before the slow indexing finishes.
    # Generous bound: half the indexing duration.
    assert when_returned < SLOW_S / 2, (
        f"/health returned {when_returned:.2f}s after start while /api/index-files "
        f"was blocking ({SLOW_S}s) — event loop is blocked."
    )


@pytest.mark.asyncio
async def test_reindex_file_does_not_block_event_loop(slow_app, dummy_pdf):
    """/health must respond during a slow /api/reindex-file call."""

    async def kick_reindex(ac):
        return await ac.post(
            "/api/reindex-file",
            json={"path": str(dummy_pdf)},
            timeout=10.0,
        )

    health, when_returned, reindex_resp = await _measure_health_during(slow_app, kick_reindex)

    assert health.status_code == 200
    assert reindex_resp.status_code == 200
    assert when_returned < SLOW_S / 2, (
        f"/health returned {when_returned:.2f}s after start while /api/reindex-file "
        f"was blocking ({SLOW_S}s) — event loop is blocked."
    )

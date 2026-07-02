"""Tests for SidecarClient timeout handling (issue #304).

The MCP SidecarClient must survive a slow-but-successful sidecar: warm
reranked searches take 5-7s, longer than httpx's 5s default timeout. A
read timeout must surface an actionable message instead of an unhandled
exception (which reaches Claude as an empty "Error executing tool"), and
the client must be configured with a generous timeout so the ceiling
isn't hit for a normal search that the sidecar answers with 200 OK.
"""
import argparse
import sys

import httpx
import pytest

# Prevent argparse from reading pytest's arguments (mirrors test_mcp_tools).
sys.argv = ["mcp_server.py"]

import mcp_server
from mcp_server import SidecarClient


def _args():
    return argparse.Namespace(sidecar_url="http://localhost:8420", data_dir=None)


class _RaisingClient:
    """Fake httpx.AsyncClient whose requests always raise a given exception."""

    def __init__(self, exc, **kwargs):
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        raise self._exc

    async def post(self, *a, **k):
        raise self._exc


@pytest.mark.asyncio
async def test_post_returns_message_on_read_timeout(monkeypatch):
    """A slow (read-timeout) search must return a string, not raise."""
    monkeypatch.setattr(
        mcp_server.httpx,
        "AsyncClient",
        lambda **k: _RaisingClient(httpx.ReadTimeout("slow"), **k),
    )
    result = await SidecarClient(_args()).post("/api/search", {"query": "x"})
    assert isinstance(result, str)
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_get_returns_message_on_read_timeout(monkeypatch):
    """The same guard applies to GET requests."""
    monkeypatch.setattr(
        mcp_server.httpx,
        "AsyncClient",
        lambda **k: _RaisingClient(httpx.ReadTimeout("slow"), **k),
    )
    result = await SidecarClient(_args()).get("/api/sources")
    assert isinstance(result, str)
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_client_configured_with_generous_timeout(monkeypatch):
    """The client must not rely on httpx's 5s default (shorter than a warm
    reranked search); it must pass an explicit, generous timeout."""
    captured = {}

    class _OK:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", _OK)
    await SidecarClient(_args()).post("/api/search", {"query": "x"})

    assert "timeout" in captured, "AsyncClient must be given an explicit timeout"
    t = captured["timeout"]
    seconds = t if isinstance(t, (int, float)) else getattr(t, "read", None)
    assert seconds is not None and seconds >= 30

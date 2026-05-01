"""
Tests for /api/mcp-heartbeat and /api/mcp-status.

The heartbeat endpoint is pinged by the MCP server every ~30s; the status
endpoint reflects whether the desktop UI should consider an agent connected
(heartbeat fresh) and whether it's actively querying (X-Source: mcp seen on
/api/search recently).
"""


def test_mcp_status_initially_disconnected(client):
    """Fresh sidecar — no heartbeat ever — should report disconnected."""
    response = client.get("/api/mcp-status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["active"] is False
    assert data["last_heartbeat_at"] is None
    assert data["last_query_at"] is None


def test_heartbeat_sets_connected(client):
    """Posting a heartbeat should flip connected=True and stamp last_heartbeat_at."""
    hb = client.post("/api/mcp-heartbeat")
    assert hb.status_code == 200
    assert hb.json() == {"ok": True}

    status = client.get("/api/mcp-status").json()
    assert status["connected"] is True
    assert status["active"] is False
    assert status["last_heartbeat_at"] is not None


def test_search_with_mcp_header_sets_active(client, sample_pdf_path):
    """A search request tagged X-Source: mcp should bump last_query_at and
    flip the active flag (active is true for 5s after a query)."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})

    client.post(
        "/api/search",
        json={"query": "dragon", "n_results": 3},
        headers={"X-Source": "mcp"},
    )

    status = client.get("/api/mcp-status").json()
    assert status["active"] is True
    assert status["last_query_at"] is not None


def test_search_without_mcp_header_does_not_set_active(client, sample_pdf_path):
    """Desktop-UI search (no X-Source header) must not register as MCP activity."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})

    client.post("/api/search", json={"query": "dragon", "n_results": 3})

    status = client.get("/api/mcp-status").json()
    assert status["active"] is False
    assert status["last_query_at"] is None

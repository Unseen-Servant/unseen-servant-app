"""
Health endpoint tests.

This is the best file to write first (after chunking) because:
1. It has zero dependencies on ChromaDB data
2. It verifies the TestClient fixture works
3. It builds confidence before tackling complex tests

Pattern: Arrange-Act-Assert
- Arrange: get the test client (fixture does this)
- Act: make the HTTP request
- Assert: check the response
"""


def test_health_returns_ok(client):
    """GET /health should return 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# CORS contract — sidecar accepts only known Tauri origins
# ---------------------------------------------------------------------------

def test_cors_accepts_tauri_localhost(client):
    """Production webview origin must be allowed."""
    response = client.options(
        "/health",
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "tauri://localhost"


def test_cors_accepts_dev_origin(client):
    """Vite dev server origin (per tauri.conf.json devUrl) must be allowed."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:1420",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:1420"


def test_cors_rejects_unknown_origin(client):
    """A random origin must not be echoed back as allowed."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI/Starlette returns 400 on disallowed CORS preflight; the
    # important assertion is that no allow-origin header is granted.
    assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"
    assert response.headers.get("access-control-allow-origin") != "*"

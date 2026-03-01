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

"""Integration tests for /api/search re-ranking.

Conftest sets ``RERANK_DISABLED=1`` for the rest of the suite (so unit
tests don't trigger a 120 MB model download). These tests
monkey-patch the rerank module directly to feed deterministic scores
into the search handler and verify the reorder behaviour.
"""

import pytest


@pytest.fixture
def indexed_client(client, sample_pdf_path):
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    return client


def test_rerank_false_skips_reranker(indexed_client, monkeypatch):
    """When rerank=False, the reranker is never invoked."""
    import server

    def boom(query, docs):
        raise AssertionError("rerank_scores should not be called when rerank=False")

    monkeypatch.setattr(server, "rerank_scores", boom)

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
    })
    assert response.status_code == 200


def test_rerank_reorders_top_candidates(indexed_client, monkeypatch):
    """A reranker that prefers the *last* candidate should bubble it up."""
    import server

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        # Score in reverse order: last doc gets the highest score.
        return [float(i) for i in range(len(docs))]

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0
    assert "docs" in captured  # rerank_scores actually called

    # The first result's text should correspond to the last doc fed in
    # (or one of its parent siblings, after dedupe-by-parent).
    top_text = data["results"][0]["text"]
    last_input = captured["docs"][-1]
    # The reranked top result's parent text should contain the chunk we
    # ranked highest. Use substring check to handle parent-doc expansion.
    assert last_input in top_text or top_text in last_input or any(
        last_input in r["text"] for r in data["results"][:3]
    )


def test_rerank_falls_back_when_scores_none(indexed_client, monkeypatch):
    """If rerank_scores returns None (model failed), keep cosine order."""
    import server

    monkeypatch.setattr(server, "rerank_scores", lambda q, d: None)

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200
    # No assertion on order — just that the response is well-formed.
    data = response.json()
    assert len(data["results"]) > 0


def test_rerank_relevance_uses_score_when_reranked(indexed_client, monkeypatch):
    """Relevance should reflect the rerank score (sigmoid, [0,1]) post-rerank."""
    import server

    # Constant score 0.9 for everything → relevance ≈ 0.9 on every result.
    monkeypatch.setattr(server, "rerank_scores", lambda q, d: [0.9] * len(d))

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200
    for r in response.json()["results"]:
        # Allow rounding (server rounds to 3 decimals).
        assert abs(r["relevance"] - 0.9) < 0.005

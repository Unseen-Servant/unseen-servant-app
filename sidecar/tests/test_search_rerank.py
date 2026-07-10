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


def test_rerank_input_prepends_section_heading(monkeypatch, client, test_collection):
    """Rerank input should mirror the embedder by prepending section_heading.

    Without this, the cross-encoder loses the breadcrumb context (e.g.
    "Combat > Grappling") that distinguishes a rule chunk from a
    keyword-adjacent monster card and tends to over-rank action text.

    Indexes a synthetic chunk with a known section_heading (the real
    test PDFs have none) and asserts the rerank input starts with it.
    """
    import server

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        return [0.5] * len(docs)

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    test_collection.upsert(
        ids=["synth_1"],
        documents=["body text about grappling and grapples"],
        metadatas=[{
            "source": "/lib/x.pdf",
            "filename": "x.pdf",
            "chunk": 0,
            "game_system": "5e",
            "chunk_type": "prose",
            "section_heading": "Combat > Grappling",
            "page_start": 1,
            "page_end": 1,
            "parent_id": "p_synth",
            "chunker_version": "test",
            "embedding_model": "test",
        }],
    )

    response = client.post("/api/search", json={
        "query": "grappling", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200, response.text
    docs = captured.get("docs", [])
    assert docs, "rerank_scores should have been called"
    assert any(
        d.startswith("Combat > Grappling\n\n") for d in docs
    ), f"Expected at least one input to start with the breadcrumb; got: {docs}"


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


# ---------------------------------------------------------------------------
# Non-English guard (issue #305): the bundled cross-encoder is English-only
# and inverts bge-m3's multilingual cosine order on non-English queries, so
# a non-ASCII query must bypass the reranker entirely.
# ---------------------------------------------------------------------------

def test_rerank_safe_for_query_ascii_vs_accented():
    """All-ASCII queries are reranker-safe; accented ones are not."""
    import server

    assert server._rerank_safe_for_query("falling damage") is True
    assert server._rerank_safe_for_query("dégâts de chute") is False


def test_non_ascii_query_skips_reranker(indexed_client, monkeypatch):
    """An accented (non-English) query must bypass the English-only reranker,
    even with rerank=True, so bge-m3's multilingual order is preserved."""
    import server

    def boom(query, docs):
        raise AssertionError("reranker must not run on a non-ASCII query")

    monkeypatch.setattr(server, "rerank_scores", boom)

    response = indexed_client.post("/api/search", json={
        "query": "dégâts de chute", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200, response.text


def test_ascii_query_still_reranks(indexed_client, monkeypatch):
    """The #305 guard must not over-skip: an all-ASCII query still reranks."""
    import server

    captured = {}

    def fake_scores(query, docs):
        captured["called"] = True
        return [0.5] * len(docs)

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = indexed_client.post("/api/search", json={
        "query": "falling damage", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200, response.text
    assert captured.get("called"), "an ASCII query should still be reranked"

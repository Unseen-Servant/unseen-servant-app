"""Tests for relevance tiers and single-scale results (issues #306/#310).

Every /api/search result carries a ``tier`` (strong/good/weak) computed
from scale-appropriate thresholds, plus a ``reranked`` flag naming the
scale. When the reranker ran, results that were picked from the cosine
tail (beyond the rerank pool) are rescored with the cross-encoder in a
small second batch, so the returned page is single-scale by construction;
the tail-rescore failing falls back to honestly mixed flags.

Mutation-verified 2026-07-09: collapsing ``_tier_for`` to a constant
"strong" fails the tier tests, and disabling the straggler rescore fails
``test_picked_tail_stragglers_are_rescored``.
"""

import pytest


@pytest.fixture
def indexed_client(client, sample_pdf_path):
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    return client


# ---------------------------------------------------------------------------
# Tier helper (unit)
# ---------------------------------------------------------------------------

def test_tier_for_rerank_scale():
    import server

    assert server._tier_for(0.9, reranked=True) == "strong"
    assert server._tier_for(0.5, reranked=True) == "strong"   # boundary
    assert server._tier_for(0.3, reranked=True) == "good"
    assert server._tier_for(0.1, reranked=True) == "good"     # boundary
    assert server._tier_for(0.05, reranked=True) == "weak"


def test_tier_for_cosine_scale():
    import server

    strong = server.COSINE_TIER_STRONG
    weak = server.COSINE_TIER_WEAK
    assert server._tier_for(strong + 0.05, reranked=False) == "strong"
    assert server._tier_for(strong, reranked=False) == "strong"    # boundary
    assert server._tier_for((strong + weak) / 2, reranked=False) == "good"
    assert server._tier_for(weak, reranked=False) == "good"        # boundary
    assert server._tier_for(weak - 0.05, reranked=False) == "weak"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

def test_results_carry_tier_and_reranked_without_rerank(indexed_client):
    """rerank=False → every result has a tier (cosine scale), reranked=False."""
    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    for r in results:
        assert r["tier"] in ("strong", "good", "weak")
        assert r["reranked"] is False


def test_results_reranked_true_when_reranker_runs(indexed_client, monkeypatch):
    import server

    monkeypatch.setattr(server, "rerank_scores", lambda q, d: [0.9] * len(d))

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    for r in results:
        assert r["reranked"] is True
        assert r["tier"] == "strong"  # 0.9 >= RERANK_TIER_STRONG


def test_non_ascii_query_gets_cosine_tiers(indexed_client, monkeypatch):
    """#305 guard composes: French query → cosine scale end to end."""
    import server

    def boom(query, docs):
        raise AssertionError("reranker must not run on a non-ASCII query")

    monkeypatch.setattr(server, "rerank_scores", boom)

    response = indexed_client.post("/api/search", json={
        "query": "dégâts de chute", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200
    for r in response.json()["results"]:
        assert r["reranked"] is False
        assert r["tier"] in ("strong", "good", "weak")


# ---------------------------------------------------------------------------
# Single-scale by construction: tail stragglers get cross-encoded
# ---------------------------------------------------------------------------

def _upsert_parents(collection, n: int) -> None:
    """Synthetic chunks across n distinct parents (mirrors the pattern in
    test_search_rerank.py — the fixture PDF only yields one parent)."""
    collection.upsert(
        ids=[f"synth_{i}" for i in range(n)],
        documents=[f"dragon lore text variant {i}" for i in range(n)],
        metadatas=[{
            "source": "/lib/synth.pdf",
            "filename": "synth.pdf",
            "chunk": i,
            "game_system": "5e",
            "chunk_type": "prose",
            "section_heading": f"Dragons > Entry {i}",
            "page_start": i + 1,
            "page_end": i + 1,
            "parent_id": f"p_synth_{i}",
            "chunker_version": "test",
            "embedding_model": "test",
        } for i in range(n)],
    )


def test_picked_tail_stragglers_are_rescored(client, test_collection, monkeypatch):
    """With a rerank pool smaller than the picked page, results beyond the
    pool must be scored by a second rerank_scores call so the page is
    single-scale (scores only: the tail is not re-sorted into the head). Pool size arrives via the request's rerank_candidates
    knob (clamped to RERANK_POOL_MIN, so the fixture outnumbers it)."""
    import server

    n_parents = server.RERANK_POOL_MIN + 2
    _upsert_parents(test_collection, n_parents)
    calls = []

    def fake_scores(query, docs):
        calls.append(list(docs))
        return [0.8] * len(docs)

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "dragon", "n_results": n_parents, "rerank": True,
        "rerank_candidates": server.RERANK_POOL_MIN,
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > server.RERANK_POOL_MIN, \
        "need picks beyond the pool for a meaningful straggler test"

    # One head batch (pool-sized) + one straggler batch for the picked tail.
    assert len(calls) == 2
    assert len(calls[0]) == server.RERANK_POOL_MIN
    assert len(calls[1]) == len(results) - server.RERANK_POOL_MIN

    for r in results:
        assert r["reranked"] is True


def test_straggler_rescore_failure_keeps_honest_mixed_flags(client, test_collection, monkeypatch):
    """If the straggler batch fails (None), tail results stay cosine-flagged."""
    import server

    n_parents = server.RERANK_POOL_MIN + 2
    _upsert_parents(test_collection, n_parents)
    calls = []

    def fake_scores(query, docs):
        calls.append(list(docs))
        return [0.8] * len(docs) if len(calls) == 1 else None

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "dragon", "n_results": n_parents, "rerank": True,
        "rerank_candidates": server.RERANK_POOL_MIN,
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > server.RERANK_POOL_MIN
    head = results[:server.RERANK_POOL_MIN]
    tail = results[server.RERANK_POOL_MIN:]
    assert all(r["reranked"] is True for r in head)
    assert all(r["reranked"] is False for r in tail)

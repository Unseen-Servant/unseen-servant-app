"""Tests for relevance tiers and single-scale results (issues #306/#310).

Every /api/search result carries a ``tier`` (strong/good/weak) computed
from scale-appropriate thresholds, plus a ``reranked`` flag naming the
scale. Since #340 the candidate pool is deduped to unique parents before
the cross-encoder runs and the scored pool is floored at n_results, so a
returned page is single-scale from one rerank pass — there is no cosine
tail to rescore; the reranker failing falls back to honest cosine flags.

Mutation-verified 2026-07-09: collapsing ``_tier_for`` to a constant
"strong" fails the tier tests.
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
# Single-scale by construction: one rerank pass covers the whole page (#340)
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


def test_page_is_single_scale_from_one_pass(client, test_collection, monkeypatch):
    """Even with the pool cap below n_results, the scored pool is floored
    at n_results parents: one rerank call, every result reranked, page
    sorted by relevance."""
    import server

    _upsert_parents(test_collection, 4)
    calls = []

    def fake_scores(query, docs):
        calls.append(list(docs))
        return [0.8 - 0.1 * i for i in range(len(docs))]

    monkeypatch.setattr(server, "RERANK_CANDIDATE_POOL", 1)
    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > 1, "need >1 parent for a meaningful single-scale test"

    # One pass covering every picked result — no straggler batch.
    assert len(calls) == 1
    assert len(calls[0]) >= len(results)

    for r in results:
        assert r["reranked"] is True

    # Single scale → the list must be sorted by relevance, descending.
    relevances = [r["relevance"] for r in results]
    assert relevances == sorted(relevances, reverse=True)


def test_rerank_failure_keeps_honest_cosine_flags(client, test_collection, monkeypatch):
    """If the rerank pass fails (None), the whole page stays cosine-flagged."""
    import server

    _upsert_parents(test_collection, 4)
    monkeypatch.setattr(server, "rerank_scores", lambda q, d: None)

    response = client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > 1
    assert all(r["reranked"] is False for r in results)

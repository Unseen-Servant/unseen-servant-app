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
# Rerank after parent-dedupe (issue #340): the candidate pool is deduped
# to unique parents *before* the cross-encoder runs, scores a pool
# proportional to n_results, and every returned result is on the
# cross-encoder scale from a single pass — no straggler rescore. Each
# parent is represented by up to two slices (cross-encoder scores on
# near-duplicate slices are noisy; the parent takes its best slice's
# score) instead of every slice.
# ---------------------------------------------------------------------------

def _upsert_synthetic(collection, entries):
    """Upsert synthetic chunks. entries = [(parent_id, text), ...]."""
    collection.upsert(
        ids=[f"synth_{i}" for i in range(len(entries))],
        documents=[text for _, text in entries],
        metadatas=[{
            "source": "/lib/synth.pdf",
            "filename": "synth.pdf",
            "chunk": i,
            "game_system": "5e",
            "chunk_type": "prose",
            "section_heading": "",
            "page_start": i + 1,
            "page_end": i + 1,
            "parent_id": pid,
            "chunker_version": "test",
            "embedding_model": "test",
        } for i, (pid, _) in enumerate(entries)],
    )


def test_rerank_scores_at_most_two_slices_per_parent(client, test_collection, monkeypatch):
    """The cross-encoder input holds at most two slices per parent — the
    two best-ranked ones stand in for the whole parent."""
    import server

    _upsert_synthetic(test_collection, [
        ("p_multi", "fire drake breathes fire in a cone MULTI one"),
        ("p_multi", "fire drake breathes fire in a cone MULTI two"),
        ("p_multi", "fire drake breathes fire in a cone MULTI three"),
        ("p_multi", "fire drake breathes fire in a cone MULTI four"),
        ("p_a", "goblin ambush tactics in the deep forest"),
        ("p_b", "healing potion prices at the village market"),
    ])

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        return [0.5] * len(docs)

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "fire drake breath", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200, response.text
    docs = captured.get("docs", [])
    assert docs, "rerank_scores should have been called"
    multi_slices = [d for d in docs if "MULTI" in d]
    assert len(multi_slices) == 2, (
        f"expected exactly two representative slices for p_multi, "
        f"got {len(multi_slices)}: {docs}"
    )


def test_parent_ranked_by_its_best_slice(client, test_collection, monkeypatch):
    """A parent whose best-cosine slice scores poorly must still win when
    its second slice scores high (max-pool over the representatives)."""
    import server

    # The DULL slice nearly restates the query, so it is deterministically
    # the parent's best-cosine representative; SHARP is semantically
    # related but lexically distant, so it can only enter the rerank input
    # as the parent's second slice.
    _upsert_synthetic(test_collection, [
        ("p_two", "fire drake breath attack DULL cone of flame"),
        ("p_two", "the ancient wyrm exhales a scorching SHARP torrent"),
        ("p_one", "fire drake breath attack OTHER entry"),
    ])

    def fake_scores(query, docs):
        return [
            0.9 if "SHARP" in d else 0.1 if "DULL" in d else 0.5
            for d in docs
        ]

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "fire drake breath", "n_results": 2, "rerank": True,
    })
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 2
    # p_two's best slice (0.9) beats p_one (0.5); its relevance reflects
    # the best slice, not the best-cosine one.
    assert results[0]["relevance"] == pytest.approx(0.9, abs=0.005)
    assert results[1]["relevance"] == pytest.approx(0.5, abs=0.005)


def test_rerank_single_pass_covers_all_results(client, test_collection, monkeypatch):
    """One rerank call per search, even when the slice pool is dominated by
    a single parent and the cap is small: unique parents are deduped first,
    so no picked result can come from beyond the scored pool (the straggler
    rescore of #306 is gone by construction)."""
    import server

    _upsert_synthetic(test_collection, [
        ("p_big", f"fire drake breathes fire in a cone variant {i}")
        for i in range(4)
    ] + [
        ("p_a", "goblin ambush tactics in the deep forest"),
        ("p_b", "healing potion prices at the village market"),
        ("p_c", "sailing ship cargo manifest and port fees"),
    ])

    calls = []

    def fake_scores(query, docs):
        calls.append(list(docs))
        return [0.8] * len(docs)

    # Old behavior: pool=2 covered only slices of p_big, so picked tail
    # parents needed a second straggler call. New behavior must floor the
    # parent pool at n_results and finish in one pass.
    monkeypatch.setattr(server, "RERANK_CANDIDATE_POOL", 2)
    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "fire drake breath", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 3
    assert len(calls) == 1, f"expected a single rerank pass, got {len(calls)}"
    for r in results:
        assert r["reranked"] is True


def test_rerank_inputs_capped_primaries_first(client, test_collection, monkeypatch):
    """RERANK_CANDIDATE_POOL caps *total* cross-encoder inputs (the old
    worst case). When it binds, primary slices win over second slices, so
    parent coverage is never sacrificed for backups."""
    import server

    _upsert_synthetic(test_collection, [
        (f"p_{i}", f"dragon lore text variant {i} slice {s}")
        for i in range(6) for s in range(2)
    ])

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        return [0.5] * len(docs)

    monkeypatch.setattr(server, "RERANK_CANDIDATE_POOL", 4)
    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "dragon", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200, response.text
    docs = captured.get("docs", [])
    assert docs, "rerank_scores should have been called"
    assert len(docs) == 4, (
        f"expected the input cap (4) to bind, got {len(docs)} inputs"
    )
    # All four slots go to primaries of distinct parents — no backups.
    assert len({d.split(" slice ")[0] for d in docs}) == 4


def test_rerank_pool_scales_with_n_results(client, test_collection, monkeypatch):
    """The scored pool is ~3× n_results unique parents, not a flat 50."""
    import server

    _upsert_synthetic(test_collection, [
        (f"p_{i}", f"dragon lore text variant {i}") for i in range(12)
    ])

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        return [0.5] * len(docs)

    monkeypatch.setattr(server, "rerank_scores", fake_scores)

    response = client.post("/api/search", json={
        "query": "dragon", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200, response.text
    docs = captured.get("docs", [])
    assert docs, "rerank_scores should have been called"
    assert len(docs) == 9, (
        f"expected 3 * n_results = 9 unique parents scored, got {len(docs)}"
    )


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

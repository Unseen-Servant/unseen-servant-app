"""Integration tests for /api/search re-ranking.

Conftest sets ``RERANK_DISABLED=1`` for the rest of the suite (so unit
tests don't trigger a ~23 MB model download). These tests
monkey-patch the rerank module directly to feed deterministic scores
into the search handler and verify the reorder behaviour.
"""


def test_rerank_false_skips_reranker(indexed_client, monkeypatch):
    """When rerank=False, the reranker is never invoked."""
    from legend_lore import service

    def boom(query, docs):
        raise AssertionError("rerank_scores should not be called when rerank=False")

    monkeypatch.setattr(service, "rerank_scores", boom)

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
    })
    assert response.status_code == 200


def _seeded_headings(client, test_store, test_embed_fn, **request):
    """Section headings of a 3-section search, in result order. The
    fixture PDF is one section, too few to show a reorder."""
    from tests.conftest import seed_parents

    seed_parents(test_store, test_embed_fn, 3)
    response = client.post("/api/search", json={"query": "dragon", "n_results": 3, **request})
    assert response.status_code == 200, response.text
    return [r["section_heading"] for r in response.json()["results"]], response.json()["results"]


def test_rerank_reorders_top_candidates(client, test_store, test_embed_fn, monkeypatch):
    """A reranker that prefers the *last* candidate should bubble it up:
    scores rising with input position reverse the order it was given."""
    from legend_lore import service

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        return [float(i) for i in range(len(docs))]

    monkeypatch.setattr(service, "rerank_scores", fake_scores)

    headings, results = _seeded_headings(client, test_store, test_embed_fn, rerank=True)
    given = [d.split("\n\n", 1)[0] for d in captured["docs"]]
    assert len(given) == 3
    assert headings == list(reversed(given))
    assert all(r["reranked"] for r in results)


def test_rerank_input_prepends_section_heading(
    monkeypatch, client, test_store, test_embed_fn
):
    """Rerank input should mirror the embedder by prepending section_heading.

    Without this, the cross-encoder loses the breadcrumb context (e.g.
    "Combat > Grappling") that distinguishes a rule chunk from a
    keyword-adjacent monster card and tends to over-rank action text.

    Indexes a synthetic chunk with a known section_heading (the real
    test PDFs have none) and asserts the rerank input starts with it.
    """
    from legend_lore import service

    captured = {}

    def fake_scores(query, docs):
        captured["docs"] = list(docs)
        return [0.5] * len(docs)

    monkeypatch.setattr(service, "rerank_scores", fake_scores)

    from legend_lore.granularity import EmbedUnit
    from tests.conftest import seed_book

    seed_book(test_store, test_embed_fn, "/lib/x.pdf", [EmbedUnit(
        chunk_id="synth_1", text="body text about grappling and grapples",
        parent_id="p_synth", chunk_type="prose",
        section_heading="Combat > Grappling", source_pdf="/lib/x.pdf",
        page_start=1, page_end=1, ordinal=0,
    )], game_system="5e")

    response = client.post("/api/search", json={
        "query": "grappling", "n_results": 3, "rerank": True,
    })
    assert response.status_code == 200, response.text
    docs = captured.get("docs", [])
    assert docs, "rerank_scores should have been called"
    assert any(
        d.startswith("Combat > Grappling\n\n") for d in docs
    ), f"Expected at least one input to start with the breadcrumb; got: {docs}"


def test_rerank_falls_back_when_scores_none(client, test_store, test_embed_fn, monkeypatch):
    """If rerank_scores returns None (model failed), keep cosine order."""
    from legend_lore import service

    cosine, _ = _seeded_headings(client, test_store, test_embed_fn, rerank=False)

    monkeypatch.setattr(service, "rerank_scores", lambda q, d: None)
    response = client.post("/api/search", json={"query": "dragon", "n_results": 3, "rerank": True})
    results = response.json()["results"]

    assert [r["section_heading"] for r in results] == cosine
    assert not any(r["reranked"] for r in results)


def test_rerank_relevance_uses_score_when_reranked(indexed_client, monkeypatch):
    """Relevance should reflect the rerank score (sigmoid, [0,1]) post-rerank."""
    from legend_lore import service

    # Constant score 0.9 for everything → relevance ≈ 0.9 on every result.
    monkeypatch.setattr(service, "rerank_scores", lambda q, d: [0.9] * len(d))

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
    from legend_lore import service

    assert service._rerank_safe_for_query("falling damage") is True
    assert service._rerank_safe_for_query("dégâts de chute") is False


def test_non_ascii_query_skips_reranker(indexed_client, monkeypatch):
    """An accented (non-English) query must bypass the English-only reranker,
    even with rerank=True, so bge-m3's multilingual order is preserved."""
    from legend_lore import service

    def boom(query, docs):
        raise AssertionError("reranker must not run on a non-ASCII query")

    monkeypatch.setattr(service, "rerank_scores", boom)

    response = indexed_client.post("/api/search", json={
        "query": "dégâts de chute", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200, response.text


def test_ascii_query_still_reranks(indexed_client, monkeypatch):
    """The #305 guard must not over-skip: an all-ASCII query still reranks."""
    from legend_lore import service

    captured = {}

    def fake_scores(query, docs):
        captured["called"] = True
        return [0.5] * len(docs)

    monkeypatch.setattr(service, "rerank_scores", fake_scores)

    response = indexed_client.post("/api/search", json={
        "query": "falling damage", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200, response.text
    assert captured.get("called"), "an ASCII query should still be reranked"

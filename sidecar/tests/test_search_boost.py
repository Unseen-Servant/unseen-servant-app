"""Game-system soft-boost for /api/search (2026-07-01 roadmap quick-win).

When the query text names a game system ("Fireball damage in 5E SRD"),
results whose PDF belongs to that system move to the front as a stable
partition, before rerank (so they fill its pool) and after it (roadmap
3.3; it replaced ×1.5/×0.7 multipliers a saturated cross-encoder score
could beat). Never a filter, and ordering only: reported relevance/tier
stay on the honest model scale. The boost is a no-op when the query names no system, and is
skipped entirely when the request already filters by game system or
source file.

Query-side only: a chunk's system comes from its metadata tag, falling
back to manifest tags and then to keyword detection on the source path —
so libraries indexed before a KNOWN_SYSTEMS keyword existed benefit
without a re-index.
"""

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# KNOWN_SYSTEMS keyword gap (the roadmap blocker)
# ---------------------------------------------------------------------------

def test_black_flag_detects_as_5e():
    import server

    assert server.detect_game_system(
        Path("/corpus/Black-Flag-Roleplaying.pdf")) == "D&D 5E"


def test_srd_cc_detects_as_5e():
    import server

    assert server.detect_game_system(
        Path("/corpus/SRD_CC_v5.1.pdf")) == "D&D 5E"


# ---------------------------------------------------------------------------
# detect_systems_in_query (unit)
# ---------------------------------------------------------------------------

def test_query_naming_5e_srd_detects_5e():
    import server

    assert server.detect_systems_in_query(
        "Fireball damage in 5E SRD") == {"D&D 5E"}


def test_query_naming_black_flag_detects_5e():
    import server

    assert server.detect_systems_in_query(
        "Initiative roll in Black Flag") == {"D&D 5E"}


def test_query_naming_basic_fantasy_detects_osr():
    import server

    assert server.detect_systems_in_query(
        "Cloud Dragon stats in Basic Fantasy") == {"OSR"}


def test_query_without_system_mention_detects_nothing():
    import server

    assert server.detect_systems_in_query(
        "how does grappling work") == set()


def test_query_naming_two_systems_detects_both():
    import server

    assert server.detect_systems_in_query(
        "convert a dnd 5e monster to pathfinder 2e") == {"D&D 5E", "PF2E"}


# ---------------------------------------------------------------------------
# /api/search ordering (integration, deterministic fake candidate pool)
# ---------------------------------------------------------------------------

def _meta(parent_id: str, filename: str, game_system: str) -> dict:
    return {
        "parent_id": parent_id,
        "filename": filename,
        "source": f"/corpus/{filename}",
        "game_system": game_system,
        "section_heading": "",
        "page_start": 1,
        "page_end": 1,
    }

# Wrong-system chunk wins on raw cosine (distance 0.10 < 0.30); the
# right-system chunk should win once partitioned to the front.
FAKE_RESULTS = {
    "ids": [["c-osr", "c-srd"]],
    "documents": [["osr fireball text", "srd fireball text"]],
    "metadatas": [[
        _meta("p-osr", "Basic-Fantasy-RPG-Rules-r142.pdf", "OSR"),
        _meta("p-srd", "SRD_CC_v5.1.pdf", "D&D 5E"),
    ]],
    "distances": [[0.10, 0.30]],
}


@pytest.fixture
def fake_pool_client(client, test_collection, monkeypatch):
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: FAKE_RESULTS)
    return client


def _search(client, **overrides):
    payload = {
        "query": "Fireball damage in 5E SRD",
        "n_results": 2,
        "rerank": False,
        **overrides,
    }
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["results"]


def test_boost_promotes_matching_system(fake_pool_client):
    results = _search(fake_pool_client)
    assert [r["filename"] for r in results] == [
        "SRD_CC_v5.1.pdf", "Basic-Fantasy-RPG-Rules-r142.pdf"]


def test_boost_pulls_matching_system_into_top_n(fake_pool_client):
    """The reorder happens on the over-fetched pool, before the top-N
    cut — a matching-system chunk beyond n_results can still surface."""
    results = _search(fake_pool_client, n_results=1)
    assert [r["filename"] for r in results] == ["SRD_CC_v5.1.pdf"]


def test_no_system_mentioned_keeps_raw_order(fake_pool_client):
    results = _search(fake_pool_client, query="fireball damage")
    assert [r["filename"] for r in results] == [
        "Basic-Fantasy-RPG-Rules-r142.pdf", "SRD_CC_v5.1.pdf"]


def test_game_system_filter_skips_boost(fake_pool_client):
    """An explicit system filter means the user already scoped the
    search — the boost must not reorder within it."""
    results = _search(fake_pool_client, game_systems=["D&D 5E"])
    assert [r["filename"] for r in results] == [
        "Basic-Fantasy-RPG-Rules-r142.pdf", "SRD_CC_v5.1.pdf"]


def test_source_filter_skips_boost(client, test_collection, sample_pdf_path,
                                   monkeypatch):
    """A single-file scope can't contain a cross-system mix; skip."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: FAKE_RESULTS)
    results = _search(client, source_filter=sample_pdf_path.name)
    assert [r["filename"] for r in results] == [
        "Basic-Fantasy-RPG-Rules-r142.pdf", "SRD_CC_v5.1.pdf"]


def test_unknown_tag_falls_back_to_source_path_detection(
        client, test_collection, monkeypatch):
    """Chunks indexed before the keyword existed carry 'unknown'; the
    boost re-detects from the source path at query time (no re-index)."""
    fake = {
        "ids": [["c-osr", "c-bf"]],
        "documents": [["osr initiative text", "black flag initiative text"]],
        "metadatas": [[
            _meta("p-osr", "Basic-Fantasy-RPG-Rules-r142.pdf", "OSR"),
            _meta("p-bf", "Black-Flag-Roleplaying.pdf", "unknown"),
        ]],
        "distances": [[0.10, 0.30]],
    }
    monkeypatch.setattr(type(test_collection), "query", lambda self, **kw: fake)
    results = _search(client, query="Initiative roll in Black Flag")
    assert [r["filename"] for r in results] == [
        "Black-Flag-Roleplaying.pdf", "Basic-Fantasy-RPG-Rules-r142.pdf"]


def test_relevance_and_tier_stay_on_raw_scale(fake_pool_client):
    """The boost reorders; it must not inflate the reported scores."""
    results = _search(fake_pool_client)
    assert results[0]["relevance"] == pytest.approx(0.7)   # 1 - 0.30, unboosted
    assert results[1]["relevance"] == pytest.approx(0.9)   # 1 - 0.10, unboosted


def test_boost_applies_to_reranked_order(fake_pool_client, monkeypatch):
    """With rerank on, the partition holds over the cross-encoder
    order: the 5E chunk wins though it scores lower."""
    import server

    monkeypatch.setattr(
        server, "rerank_scores",
        lambda q, docs: [0.6 if "srd" in d else 0.8 for d in docs])
    results = _search(fake_pool_client, rerank=True)
    assert [r["filename"] for r in results] == [
        "SRD_CC_v5.1.pdf", "Basic-Fantasy-RPG-Rules-r142.pdf"]
    assert results[0]["reranked"] is True
    assert results[0]["relevance"] == pytest.approx(0.6)   # raw sigmoid


def test_boost_holds_against_a_saturated_wrong_system_score(
        fake_pool_client, monkeypatch):
    """The case the multipliers lost (q048, 2026-09-23): a wrong-system
    exact match the cross-encoder scores 0.92 beat a named-system 0.39
    (0.92×0.7 > 0.39×1.5). The partition keeps the named system first."""
    import server

    monkeypatch.setattr(
        server, "rerank_scores",
        lambda q, docs: [0.39 if "srd" in d else 0.92 for d in docs])
    results = _search(fake_pool_client, rerank=True)
    assert [r["filename"] for r in results] == [
        "SRD_CC_v5.1.pdf", "Basic-Fantasy-RPG-Rules-r142.pdf"]


def test_boost_fills_the_rerank_pool_with_the_named_system(
        client, test_collection, monkeypatch):
    """Before rerank the partition decides pool entry: a named-system
    chunk ranked below the pool size is still scored."""
    import server

    fake = {
        "ids": [["c-osr", "c-srd"]],
        "documents": [["osr text", "srd text"]],
        "metadatas": [[
            _meta("p-osr", "Basic-Fantasy-RPG-Rules-r142.pdf", "OSR"),
            _meta("p-srd", "SRD_CC_v5.1.pdf", "D&D 5E"),
        ]],
        "distances": [[0.10, 0.30]],
    }
    monkeypatch.setattr(type(test_collection), "query", lambda self, **kw: fake)
    scored = []
    monkeypatch.setattr(
        server, "rerank_scores",
        lambda q, docs: scored.extend(docs) or [0.5] * len(docs))
    _search(client, rerank=True, rerank_candidates=1)
    assert scored[0] == "srd text"

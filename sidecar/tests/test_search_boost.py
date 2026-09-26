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

from legend_lore.library_store import StoredUnit


# ---------------------------------------------------------------------------
# KNOWN_SYSTEMS keyword gap (the roadmap blocker)
# ---------------------------------------------------------------------------

def test_black_flag_detects_as_5e():
    from legend_lore import service

    assert service.detect_game_system(
        Path("/corpus/Black-Flag-Roleplaying.pdf")) == "D&D 5E"


def test_srd_cc_detects_as_5e():
    from legend_lore import service

    assert service.detect_game_system(
        Path("/corpus/SRD_CC_v5.1.pdf")) == "D&D 5E"


# ---------------------------------------------------------------------------
# detect_systems_in_query (unit)
# ---------------------------------------------------------------------------

def test_query_naming_5e_srd_detects_5e():
    from legend_lore import service

    assert service.detect_systems_in_query(
        "Fireball damage in 5E SRD") == {"D&D 5E"}


def test_query_naming_black_flag_detects_5e():
    from legend_lore import service

    assert service.detect_systems_in_query(
        "Initiative roll in Black Flag") == {"D&D 5E"}


def test_query_naming_basic_fantasy_detects_osr():
    from legend_lore import service

    assert service.detect_systems_in_query(
        "Cloud Dragon stats in Basic Fantasy") == {"OSR"}


def test_query_without_system_mention_detects_nothing():
    from legend_lore import service

    assert service.detect_systems_in_query(
        "how does grappling work") == set()


def test_query_naming_two_systems_detects_both():
    from legend_lore import service

    assert service.detect_systems_in_query(
        "convert a dnd 5e monster to pathfinder 2e") == {"D&D 5E", "PF2E"}


# ---------------------------------------------------------------------------
# strip_system_cues (unit)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("dragonbane fireball spell damage", "fireball spell damage"),
    ("how much damage does fireball do in dragonbane?",
     "how much damage does fireball do in"),
    ("Fireball damage in 5E SRD", "Fireball damage in"),
    ("Cloud Dragon stats in Basic Fantasy", "Cloud Dragon stats in"),
    ("D&D 5e grappling", "grappling"),
    ("convert a dnd 5e monster to pathfinder 2e", "convert a monster to"),
    ("castles & crusades siege engine", "siege engine"),
    # Spaced the way the Dragonbane rulebook itself prints it.
    ("dragon bane poison", "poison"),
    ("osric's paladin", "paladin"),
])
def test_named_system_is_stripped(query, expected):
    from legend_lore import service

    assert service.strip_system_cues(query) == expected


@pytest.mark.parametrize("query", [
    "how does grappling work",
    # Detection matches substrings; only whole words are stripped.
    "dragonbanes poison",
    # Nothing but the cue: searching for nothing is worse than the name.
    "dragonbane",
])
def test_query_is_kept_whole(query):
    from legend_lore import service

    assert service.strip_system_cues(query) == query


# ---------------------------------------------------------------------------
# /api/search ordering (integration, deterministic fake candidate pool)
# ---------------------------------------------------------------------------

def _unit(uid: int, text: str, parent_id: str, filename: str,
          game_system: str) -> StoredUnit:
    return StoredUnit(
        id=uid, text=text, source=f"/corpus/{filename}", filename=filename,
        game_system=game_system, ordinal=uid, parent_id=parent_id,
        chunk_type="prose", section_heading=None, page_start=1, page_end=1,
        page_label_start="", page_label_end="", section_id=None,
        section_path=None,
    )


def _fake_pool(store, monkeypatch, pool):
    """Serve ``pool`` — ``(StoredUnit, cosine distance)`` pairs, nearest
    first — as the dense ranking, whatever the query or scope."""
    units = {u.id: u for u, _ in pool}
    monkeypatch.setattr(
        store, "knn",
        lambda vector, k, doc_ids=None: [(u.id, d) for u, d in pool][:k])
    monkeypatch.setattr(
        store, "hydrate",
        lambda ids: {i: units[i] for i in ids if i in units})


# Wrong-system chunk wins on raw cosine (distance 0.10 < 0.30); the
# right-system chunk should win once partitioned to the front.
FAKE_POOL = [
    (_unit(1, "osr fireball text", "p-osr",
           "Basic-Fantasy-RPG-Rules-r142.pdf", "OSR"), 0.10),
    (_unit(2, "srd fireball text", "p-srd", "SRD_CC_v5.1.pdf", "D&D 5E"), 0.30),
]


@pytest.fixture
def fake_pool_client(client, test_store, monkeypatch):
    _fake_pool(test_store, monkeypatch, FAKE_POOL)
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


def test_source_filter_skips_boost(client, test_store, sample_pdf_path,
                                   monkeypatch):
    """A single-file scope can't contain a cross-system mix; skip."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    _fake_pool(test_store, monkeypatch, FAKE_POOL)
    results = _search(client, source_filter=sample_pdf_path.name)
    assert [r["filename"] for r in results] == [
        "Basic-Fantasy-RPG-Rules-r142.pdf", "SRD_CC_v5.1.pdf"]


def test_unknown_tag_falls_back_to_source_path_detection(
        client, test_store, monkeypatch):
    """Chunks indexed before the keyword existed carry 'unknown'; the
    boost re-detects from the source path at query time (no re-index)."""
    _fake_pool(test_store, monkeypatch, [
        (_unit(1, "osr initiative text", "p-osr",
               "Basic-Fantasy-RPG-Rules-r142.pdf", "OSR"), 0.10),
        (_unit(2, "black flag initiative text", "p-bf",
               "Black-Flag-Roleplaying.pdf", "unknown"), 0.30),
    ])
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
    from legend_lore import service

    monkeypatch.setattr(service, "rerank_scores",
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
    from legend_lore import service

    monkeypatch.setattr(service, "rerank_scores",
        lambda q, docs: [0.39 if "srd" in d else 0.92 for d in docs])
    results = _search(fake_pool_client, rerank=True)
    assert [r["filename"] for r in results] == [
        "SRD_CC_v5.1.pdf", "Basic-Fantasy-RPG-Rules-r142.pdf"]


def test_boost_fills_the_rerank_pool_with_the_named_system(
        client, test_store, monkeypatch):
    """Before rerank the partition decides pool entry: a named-system
    chunk ranked below the pool size is still scored."""
    from legend_lore import service

    _fake_pool(test_store, monkeypatch, [
        (_unit(1, "osr text", "p-osr",
               "Basic-Fantasy-RPG-Rules-r142.pdf", "OSR"), 0.10),
        (_unit(2, "srd text", "p-srd", "SRD_CC_v5.1.pdf", "D&D 5E"), 0.30),
    ])
    scored = []
    monkeypatch.setattr(service, "rerank_scores",
        lambda q, docs: scored.extend(docs) or [0.5] * len(docs))
    _search(client, rerank=True, rerank_candidates=1)
    assert scored[0] == "srd text"


def test_reranker_scores_the_query_without_its_system_cue(
        fake_pool_client, monkeypatch):
    """The named system boosts its books but is not part of what the
    cross-encoder scores against; the boost still reads the full query."""
    from legend_lore import service

    queries = []
    monkeypatch.setattr(service, "rerank_scores",
        lambda q, docs: queries.append(q) or [0.5] * len(docs))
    results = _search(fake_pool_client, rerank=True)
    assert set(queries) == {"Fireball damage in"}
    assert results[0]["filename"] == "SRD_CC_v5.1.pdf"


def test_strip_cues_off_scores_the_full_query(fake_pool_client, monkeypatch):
    from legend_lore import service

    queries = []
    monkeypatch.setattr(service, "rerank_scores",
        lambda q, docs: queries.append(q) or [0.5] * len(docs))
    _search(fake_pool_client, rerank=True, strip_cues=False)
    assert set(queries) == {"Fireball damage in 5E SRD"}

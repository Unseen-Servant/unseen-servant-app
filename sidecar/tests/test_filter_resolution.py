"""Near-miss filter resolution for /api/search (issue #309).

MCP agents guess filter values from user vernacular ("Pathfinder" vs the
tag "Pathfinder 2E", "Players Handbook.pdf" vs "Player's Handbook.pdf"),
and exact-match where-clauses turned every near-miss into a silent
zero-result response indistinguishable from a true semantic miss.
Unambiguous near-misses now auto-resolve (with a note in `message`);
ambiguous or unmatched values return an actionable message naming what
is actually available.
"""

import pytest


# ---------------------------------------------------------------------------
# _resolve_filter_value (unit)
# ---------------------------------------------------------------------------

def test_resolve_exact_match_wins():
    from legend_lore import service

    resolved, matches = service._resolve_filter_value(
        "D&D 5E", ["D&D 5E", "Dragonbane"])
    assert resolved == "D&D 5E"


def test_resolve_case_and_accent_insensitive_equality():
    from legend_lore import service

    resolved, _ = service._resolve_filter_value(
        "dragon bane", ["Dragonbane", "D&D 5E"])
    assert resolved == "Dragonbane"


def test_resolve_unique_substring():
    from legend_lore import service

    # 'dnd' is a normalized substring of 'dnd5e' only.
    resolved, _ = service._resolve_filter_value(
        "D&D", ["D&D 5E", "Dragonbane"])
    assert resolved == "D&D 5E"


def test_resolve_ambiguous_returns_candidates():
    from legend_lore import service

    resolved, matches = service._resolve_filter_value(
        "Pathfinder", ["Pathfinder 1E", "Pathfinder 2E", "Dragonbane"])
    assert resolved is None
    assert set(matches) == {"Pathfinder 1E", "Pathfinder 2E"}


def test_resolve_no_match():
    from legend_lore import service

    resolved, matches = service._resolve_filter_value(
        "Shadowrun", ["D&D 5E", "Dragonbane"])
    assert resolved is None
    assert matches == []


# ---------------------------------------------------------------------------
# /api/search integration
# ---------------------------------------------------------------------------

@pytest.fixture
def tagged_client(client, sample_pdf_path):
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    resp = client.post("/api/set-game-systems", json={
        "filename": sample_pdf_path.name, "game_systems": ["D&D 5E"],
    })
    assert resp.status_code == 200, resp.text
    return client


def test_near_miss_game_system_resolves_and_notes(tagged_client):
    resp = tagged_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
        "game_system": "dnd 5e",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"], "near-miss tag must resolve and return results"
    assert "D&D 5E" in body.get("message", "")


def test_unknown_game_system_returns_available_tags(tagged_client):
    resp = tagged_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
        "game_system": "Shadowrun",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"] == []
    assert "Shadowrun" in body.get("message", "")
    assert "D&D 5E" in body["message"]


def test_near_miss_source_filter_resolves(tagged_client, sample_pdf_path):
    # Missing extension + spacing: 'dragonbane monsters' vs
    # 'dragonbane_monsters.pdf' — normalized substring, unique.
    resp = tagged_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
        "source_filter": "dragonbane monsters",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"], "near-miss filename must resolve"
    assert sample_pdf_path.name in body.get("message", "")


def test_unknown_source_filter_returns_hint(tagged_client):
    resp = tagged_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
        "source_filter": "no_such_book.pdf",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"] == []
    assert "no_such_book.pdf" in body.get("message", "")


def test_exact_values_get_no_note(tagged_client, sample_pdf_path):
    resp = tagged_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": False,
        "game_system": "D&D 5E", "source_filter": sample_pdf_path.name,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"]
    assert not body.get("message")

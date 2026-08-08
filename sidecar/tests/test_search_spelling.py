"""/api/search spell correction (typo-tolerance design, section A).

Default-on since the 2026-07-10 eval gate passed with the
general-English protection in place (clean suite reproduces the
baseline to the digit; see evals/baselines/2026-07-10-spellfix-en-guard.md).
The corrected query must drive every downstream consumer of the query
text — the dense embed, the BM25 side when `hybrid` is on — and surface
in the response as `corrected_query` plus a note in the `message`
channel. `spell_correction: false` bypasses everything; the vocabulary
rebuilds when the chunk count changes (same trigger as the lexical
index).
"""

import pytest


def _meta(parent_id: str, filename: str) -> dict:
    return {
        "parent_id": parent_id,
        "filename": filename,
        "source": f"/corpus/{filename}",
        "game_system": "OSR",
        "section_heading": "",
        "page_start": 1,
        "page_end": 1,
    }


STAT_DOC = "the owlbear has claws and the owlbear grapples the owlbear"


@pytest.fixture
def capture_client(client, test_collection, monkeypatch):
    """One chunk giving 'owlbear' vocab frequency 3; dense query calls
    are captured so tests can assert which text was embedded."""
    test_collection.add(
        ids=["c-stat"],
        documents=[STAT_DOC],
        metadatas=[_meta("p-stat", "monsters.pdf")],
    )
    captured: dict = {}

    def fake_query(self, **kwargs):
        captured.update(kwargs)
        return {
            "ids": [["c-stat"]],
            "documents": [[STAT_DOC]],
            "metadatas": [[_meta("p-stat", "monsters.pdf")]],
            "distances": [[0.2]],
        }

    monkeypatch.setattr(type(test_collection), "query", fake_query)
    return client, captured


def _search(client, **overrides):
    payload = {
        "query": "owlber claws",
        "n_results": 5,
        "rerank": False,
        **overrides,
    }
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_typo_query_is_corrected_and_returns_results(capture_client):
    client, captured = capture_client
    body = _search(client)
    # The dense embed saw the corrected form, and the corrected query's
    # parent comes back.
    assert captured["query_texts"] == ["owlbear claws"]
    assert body["corrected_query"] == "owlbear claws"
    assert 'Query corrected to "owlbear claws".' in body["message"]
    assert [r["filename"] for r in body["results"]] == ["monsters.pdf"]


def test_clean_query_is_untouched(capture_client):
    client, captured = capture_client
    body = _search(client, query="owlbear claws")
    assert captured["query_texts"] == ["owlbear claws"]
    assert body["corrected_query"] is None
    assert "message" not in body


def test_spell_correction_false_bypasses_everything(capture_client):
    client, captured = capture_client
    body = _search(client, spell_correction=False)
    assert captured["query_texts"] == ["owlber claws"]
    assert body["corrected_query"] is None
    assert "message" not in body


def test_composes_with_hybrid(client, test_collection, monkeypatch):
    """The BM25 side must search the corrected text: 'owlber' matches
    nothing lexically, so the stat block (missed by the fake dense pool)
    only surfaces when the corrected 'owlbear' reaches FTS5."""
    prose_doc = "combat happens in rounds and each round has phases"
    test_collection.add(
        ids=["c-prose", "c-stat"],
        documents=[prose_doc, STAT_DOC],
        metadatas=[_meta("p-prose", "rules.pdf"), _meta("p-stat", "monsters.pdf")],
    )
    fake_dense = {
        "ids": [["c-prose"]],
        "documents": [[prose_doc]],
        "metadatas": [[_meta("p-prose", "rules.pdf")]],
        "distances": [[0.2]],
    }
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: fake_dense)

    corrected = _search(client, query="owlber", hybrid=True)
    assert corrected["corrected_query"] == "owlbear"
    assert {r["filename"] for r in corrected["results"]} == {
        "rules.pdf", "monsters.pdf"
    }

    bypassed = _search(
        client, query="owlber", hybrid=True, spell_correction=False)
    assert [r["filename"] for r in bypassed["results"]] == ["rules.pdf"]


def test_vocabulary_rebuilds_when_chunk_count_changes(client, test_collection):
    """Same trigger as the lexical index: a term indexed after the first
    search becomes a correction target on the next one."""
    test_collection.add(
        ids=["c1"],
        documents=[STAT_DOC],
        metadatas=[_meta("p1", "monsters.pdf")],
    )
    before = _search(client, query="grimlok lair")
    assert before["corrected_query"] is None  # 'grimlock' not indexed yet

    test_collection.add(
        ids=["c2"],
        documents=["the grimlock hears all; grimlock packs hunt; grimlock"],
        metadatas=[_meta("p2", "monsters.pdf")],
    )
    after = _search(client, query="grimlok lair")
    assert after["corrected_query"] == "grimlock lair"

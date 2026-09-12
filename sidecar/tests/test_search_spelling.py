"""/api/search spell correction (typo-tolerance design, section A).

Default-on since the 2026-07-10 eval gate passed with the
general-English protection in place (clean suite reproduces the
baseline to the digit; see evals/baselines/2026-07-10-spellfix-en-guard.md).
The corrected query must drive every downstream consumer of the query
text — the dense embed, the BM25 side when `hybrid` is on — and surface
in the response as `corrected_query` plus a note in the `message`
channel. `spell_correction: false` bypasses everything; the vocabulary
rebuilds when the manifest content digest changes; legacy stores (no
persisted FTS rows) key on the chunk count instead.
"""

import pytest

import server
import spelling
from parents_store import upsert_units_fts
from server import IndexManifest, ManifestEntry, save_manifest


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


def test_composes_with_hybrid(client, test_collection, tmp_path, monkeypatch):
    """The BM25 side must search the corrected text: 'owlber' matches
    nothing lexically, so the stat block (missed by the fake dense pool)
    only surfaces when the corrected 'owlbear' reaches FTS5."""
    prose_doc = "combat happens in rounds and each round has phases"
    test_collection.add(
        ids=["c-prose", "c-stat"],
        documents=[prose_doc, STAT_DOC],
        metadatas=[_meta("p-prose", "rules.pdf"), _meta("p-stat", "monsters.pdf")],
    )
    upsert_units_fts(tmp_path, "/corpus/rules.pdf", [
        ("c-prose", 0, "rules.pdf", "OSR", "p-prose", prose_doc)])
    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", STAT_DOC)])
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
    """A term indexed after the first search becomes a correction target
    on the next one."""
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


# ---------------------------------------------------------------------------
# Vocabulary source and invalidation (#343)
# ---------------------------------------------------------------------------

def _fake_stat_pool():
    return {
        "ids": [["c-stat"]],
        "documents": [[STAT_DOC]],
        "metadatas": [[_meta("p-stat", "monsters.pdf")]],
        "distances": [[0.2]],
    }


def _manifest(
    tmp_path, content_hash: str = "h1", sources: dict[str, int] | None = None
) -> None:
    """Write a manifest; ``sources`` maps source path -> chunk_count."""
    sources = sources or {"/corpus/monsters.pdf": 1}
    save_manifest(tmp_path, IndexManifest(files={
        path: ManifestEntry(
            filename=path.rsplit("/", 1)[-1],
            mtime=1.0,
            chunk_count=chunk_count,
            indexed_at="2026-09-12T00:00:00+00:00",
            game_system="OSR",
            content_hash=content_hash,
            pipeline_version="p1",
        )
        for path, chunk_count in sources.items()
    }))


def test_spell_vocab_comes_from_unit_fts(
    client, test_collection, tmp_path, monkeypatch
):
    """The vocabulary is read from the persisted FTS rows — whose text is
    exactly the heading-prepended embed text — not by paging the whole
    Chroma collection back over the wire."""
    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", STAT_DOC)])
    _manifest(tmp_path, "h1")

    def no_scan(*args, **kwargs):
        raise AssertionError("Chroma scanned to build the spell vocabulary")

    monkeypatch.setattr(type(test_collection), "get", no_scan)
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: _fake_stat_pool())

    body = _search(client)
    assert body["corrected_query"] == "owlbear claws"


def test_spell_vocab_invalidates_on_manifest_digest_change(
    client, test_collection, tmp_path, monkeypatch
):
    """Cached across searches, rebuilt when a re-index moves the digest."""
    import spelling

    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", STAT_DOC)])
    _manifest(tmp_path, "h1")
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: _fake_stat_pool())

    builds = []
    real_build = spelling.build_vocabulary_from_store

    def counting(data_dir):
        builds.append(data_dir)
        return real_build(data_dir)

    monkeypatch.setattr(spelling, "build_vocabulary_from_store", counting)

    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1  # same index, same vocabulary

    _manifest(tmp_path, "h2")  # re-indexed: new content hash
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 2


def test_spell_mode_is_decided_once_per_manifest_digest(
    client, test_collection, tmp_path, monkeypatch
):
    """Coverage is a cache-miss question, not a per-search one:
    `count_units_fts` is an O(rows) scan (~37 ms at 100k rows), and
    variant expansion would pay it twice per search."""
    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", STAT_DOC)])
    _manifest(tmp_path)
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: _fake_stat_pool())

    counted = []
    real_count = server.count_units_fts

    def counting(data_dir, source=None):
        counted.append(data_dir)
        return real_count(data_dir, source)

    monkeypatch.setattr(server, "count_units_fts", counting)

    assert _search(client)["corrected_query"] == "owlbear claws"
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(counted) == 1


def test_partial_fts_coverage_falls_back_to_the_chroma_scan(
    client, test_collection, tmp_path, monkeypatch
):
    """A part-migrated library (FTS rows for some books only) must not
    build the vocabulary from the migrated subset: the missing books'
    proper nouns would read as OOV and get rewritten — a change in search
    results, on a perf-only change. Full coverage or nothing."""
    test_collection.add(
        ids=["c-stat"],
        documents=[STAT_DOC],
        metadatas=[_meta("p-stat", "monsters.pdf")],
    )
    # rules.pdf has its FTS rows; monsters.pdf (which holds 'owlbear')
    # has not been re-indexed yet.
    upsert_units_fts(tmp_path, "/corpus/rules.pdf", [
        ("c-prose", 0, "rules.pdf", "OSR", "p-prose", "combat in rounds"),
        ("c-prose2", 1, "rules.pdf", "OSR", "p-prose", "each round has phases"),
    ])
    _manifest(tmp_path, sources={"/corpus/rules.pdf": 2, "/corpus/monsters.pdf": 2})

    def no_store(*args, **kwargs):
        raise AssertionError("built the vocabulary from partial FTS coverage")

    monkeypatch.setattr(spelling, "build_vocabulary_from_store", no_store)
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: _fake_stat_pool())

    assert _search(client)["corrected_query"] == "owlbear claws"


def test_spell_vocab_survives_a_chunk_count_change_with_the_same_digest(
    client, test_collection, tmp_path, monkeypatch
):
    """The negative of the invalidation test: on a migrated index the key
    is the digest, so rows appearing in Chroma without a re-index must
    not throw the vocabulary away."""
    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", STAT_DOC)])
    _manifest(tmp_path)
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: _fake_stat_pool())

    builds = []
    real_build = spelling.build_vocabulary_from_store

    def counting(data_dir):
        builds.append(data_dir)
        return real_build(data_dir)

    monkeypatch.setattr(spelling, "build_vocabulary_from_store", counting)

    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1

    test_collection.add(
        ids=["c-extra"],
        documents=["a later section about torches and rations"],
        metadatas=[_meta("p-extra", "monsters.pdf")],
    )
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1

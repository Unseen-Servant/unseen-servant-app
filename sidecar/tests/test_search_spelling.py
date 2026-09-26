"""/api/search spell correction (typo-tolerance design, section A).

Default-on since the 2026-07-10 eval gate passed with the
general-English protection in place (clean suite reproduces the
baseline to the digit; see evals/baselines/2026-07-10-spellfix-en-guard.md).
The corrected query must drive every downstream consumer of the query
text — the dense embed, the BM25 side when `hybrid` is on — and surface
in the response as `corrected_query` plus a note in the `message`
channel. `spell_correction: false` bypasses everything; the vocabulary
rebuilds when the manifest content digest changes (or, with nothing in
the manifest, when the store's unit count does).
"""

import pytest
from fastapi.testclient import TestClient

from legend_lore import spelling
from legend_lore.granularity import EmbedUnit
from legend_lore.service import IndexManifest, ManifestEntry, save_manifest
from server import create_app
from tests.conftest import TEST_EMBED_DIM, seed_book


STAT_DOC = "the owlbear has claws and the owlbear grapples the owlbear"


def _flat(texts):
    """Placeholder vectors for tests whose dense ranking is scripted."""
    return [[1.0] + [0.0] * (TEST_EMBED_DIM - 1) for _ in texts]


def _book(store, filename, *texts, heading=None, embed_fn=_flat):
    """Index `texts` as one book at /corpus/<filename>; unit ids in order."""
    path = f"/corpus/{filename}"
    units = [
        EmbedUnit(
            chunk_id=f"c{i}", text=t, parent_id=f"p-{filename}-{i}",
            chunk_type="prose", section_heading=heading, source_pdf=path,
            page_start=1, page_end=1, ordinal=i,
        )
        for i, t in enumerate(texts)
    ]
    seed_book(store, embed_fn, path, units, game_system="OSR")
    return [
        uid for (uid,) in store.conn().execute(
            "SELECT u.id FROM units u JOIN documents d ON d.id = u.document_id "
            "WHERE d.path = ? ORDER BY u.ordinal", (path,)
        )
    ]


@pytest.fixture
def dense(test_store, tmp_path, monkeypatch):
    """App whose dense side is scripted: each embed call's query texts are
    recorded in ``state["query_texts"]``, and every knn returns
    ``state["pool"]`` — (unit_id, distance) pairs."""
    state: dict = {"query_texts": None, "pool": []}

    def embed(texts):
        state["query_texts"] = list(texts)
        return _flat(texts)

    monkeypatch.setattr(
        test_store, "knn", lambda vec, k, doc_ids=None: list(state["pool"])
    )
    client = TestClient(
        create_app(store=test_store, data_dir=tmp_path, embed_fn=embed)
    )
    return client, state


@pytest.fixture
def capture_client(dense, test_store):
    """One chunk giving 'owlbear' vocab frequency 3; the embedded query
    text is captured so tests can assert which text was embedded."""
    client, state = dense
    (stat,) = _book(test_store, "monsters.pdf", STAT_DOC)
    state["pool"] = [(stat, 0.2)]
    return client, state


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


def test_composes_with_hybrid(dense, test_store):
    """The BM25 side must search the corrected text: 'owlber' matches
    nothing lexically, so the stat block (missed by the scripted dense
    pool) only surfaces when the corrected 'owlbear' reaches FTS5."""
    client, state = dense
    (prose,) = _book(
        test_store, "rules.pdf",
        "combat happens in rounds and each round has phases",
    )
    _book(test_store, "monsters.pdf", STAT_DOC)
    state["pool"] = [(prose, 0.2)]

    corrected = _search(client, query="owlber", hybrid=True)
    assert corrected["corrected_query"] == "owlbear"
    assert {r["filename"] for r in corrected["results"]} == {
        "rules.pdf", "monsters.pdf"
    }

    bypassed = _search(
        client, query="owlber", hybrid=True, spell_correction=False)
    assert [r["filename"] for r in bypassed["results"]] == ["rules.pdf"]


def test_vocabulary_rebuilds_when_chunk_count_changes(
    client, test_store, test_embed_fn
):
    """A term indexed after the first search becomes a correction target
    on the next one."""
    _book(test_store, "monsters.pdf", STAT_DOC, embed_fn=test_embed_fn)
    before = _search(client, query="grimlok lair")
    assert before["corrected_query"] is None  # 'grimlock' not indexed yet

    _book(
        test_store, "grimlocks.pdf",
        "the grimlock hears all; grimlock packs hunt; grimlock",
        embed_fn=test_embed_fn,
    )
    after = _search(client, query="grimlok lair")
    assert after["corrected_query"] == "grimlock lair"


# ---------------------------------------------------------------------------
# Vocabulary source and invalidation (#343)
# ---------------------------------------------------------------------------

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


def test_spell_vocab_counts_the_heading_prepended_text(dense, test_store, tmp_path):
    """The vocabulary is the text the embedder saw — section heading
    prepended — so a monster name that only appears as the heading above
    its stat block is still a correction target."""
    client, state = dense
    ids = _book(
        test_store, "monsters.pdf",
        "claws rend flesh", "a grapple follows", "it hunts at night",
        heading="Owlbear",
    )
    state["pool"] = [(ids[0], 0.2)]
    _manifest(tmp_path, sources={"/corpus/monsters.pdf": 3})

    assert _search(client)["corrected_query"] == "owlbear claws"


def test_spell_vocab_invalidates_on_manifest_digest_change(
    capture_client, tmp_path, monkeypatch
):
    """Cached across searches, rebuilt when a re-index moves the digest."""
    client, _ = capture_client
    _manifest(tmp_path, "h1")

    builds = []
    real_build = spelling.build_vocabulary_from_store

    def counting(store):
        builds.append(store)
        return real_build(store)

    monkeypatch.setattr(spelling, "build_vocabulary_from_store", counting)

    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1  # same index, same vocabulary

    _manifest(tmp_path, "h2")  # re-indexed: new content hash
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 2


def test_spell_vocab_survives_a_unit_count_change_with_the_same_digest(
    capture_client, test_store, tmp_path, monkeypatch
):
    """The negative of the invalidation test: with an indexed manifest the
    key is the digest, so units appearing in the store without a manifest
    change must not throw the vocabulary away."""
    client, _ = capture_client
    _manifest(tmp_path)

    builds = []
    real_build = spelling.build_vocabulary_from_store

    def counting(store):
        builds.append(store)
        return real_build(store)

    monkeypatch.setattr(spelling, "build_vocabulary_from_store", counting)

    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1

    _book(test_store, "extra.pdf", "a later section about torches and rations")
    assert _search(client)["corrected_query"] == "owlbear claws"
    assert len(builds) == 1


# --- partial searches: the GM is still typing the last word ---------------


def test_partial_completes_the_last_word_silently(capture_client):
    client, captured = capture_client
    body = _search(client, query="claws owlb", partial=True)
    assert captured["query_texts"] == ["claws owlbear"]
    assert body["completed_query"] == "claws owlbear"
    assert body["corrected_query"] is None
    assert "message" not in body          # nothing to tell a typing GM


def test_partial_never_edit_corrects_the_last_word(capture_client):
    # Committed, "owlber" is a typo for "owlbear"; mid-typing it is a
    # prefix, and no vocabulary word starts with it.
    client, captured = capture_client
    body = _search(client, query="claws owlber", partial=True)
    assert captured["query_texts"] == ["claws owlber"]
    assert body["corrected_query"] is None
    assert body["completed_query"] is None


def test_partial_still_corrects_the_words_before_the_last(capture_client):
    client, captured = capture_client
    body = _search(client, query="owlber cl", partial=True)
    assert captured["query_texts"] == ["owlbear cl"]
    assert body["corrected_query"] == "owlbear cl"


def test_committed_search_reports_no_completion(capture_client):
    client, captured = capture_client
    body = _search(client, query="claws owlb")
    assert captured["query_texts"] == ["claws owlb"]
    assert body["completed_query"] is None


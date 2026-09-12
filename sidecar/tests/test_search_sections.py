"""/api/search returns assembled sections (roadmap 2.1, server side).

A hit is answered with the whole section the matched unit belongs to —
the root chosen by `parents_store.section_root_for` — deduped by that
root rather than by parent_id, with the unit that actually matched
(`matched_text`) and its own parent (`chunk_text`) kept alongside.

The fixtures stage units directly in Chroma with hand-built metadata and
their parents in the SQLite store, then pin the dense ranking with a fake
`collection.query` — the same deterministic setup as
`test_search_hybrid.py`.
"""

import pytest

from granularity import ParentDoc
from parents_store import upsert_parents

SOURCE = "/corpus/monsters.pdf"

# A sibling monster large enough to push the "Monsters" subtree past
# SECTION_CAP, so the section root for a Kraken hit is `s_m/s_k` (the
# Kraken) rather than the whole bestiary.
DRAGON_TEXT = "Dragon lore. " * 500


def _meta(parent_id: str, section_id: str, section_path: str, heading: str) -> dict:
    return {
        "parent_id": parent_id,
        "section_id": section_id,
        "section_path": section_path,
        "filename": "monsters.pdf",
        "source": SOURCE,
        "game_system": "OSR",
        "section_heading": heading,
        "page_start": 10,
        "page_end": 10,
        # Front matter puts the printed number well ahead of the physical
        # one, as in a real book.
        "page_label_start": "326",
        "page_label_end": "326",
    }


UNITS = [
    ("u-k", "Kraken overview text",
     _meta("p-k", "s_k", "s_m/s_k", "Monsters > Kraken")),
    ("u-ka", "Tentacle attack text",
     _meta("p-ka", "s_ka", "s_m/s_k/s_ka", "Monsters > Kraken > Actions")),
    ("u-kl", "Ink cloud text",
     _meta("p-kl", "s_kl", "s_m/s_k/s_kl",
           "Monsters > Kraken > Legendary Actions")),
]

PARENT_TEXTS = {
    "p-k": "Kraken. AC 18, HP 472. A gargantuan monstrosity.",
    "p-ka": "Tentacle attack. The kraken makes three tentacle attacks.",
    "p-kl": "Ink cloud. The kraken exudes a cloud of ink underwater.",
}


def _parent(pid: str, heading: str, section_id: str | None,
            section_path: str | None, text: str | None = None,
            pages: tuple[int, int] = (10, 11)) -> ParentDoc:
    return ParentDoc(
        parent_id=pid,
        text=text if text is not None else PARENT_TEXTS[pid],
        section_heading=heading,
        chunk_type="prose",
        source_pdf=SOURCE,
        page_start=pages[0],
        page_end=pages[1],
        section_id=section_id,
        section_path=section_path,
    )


def _stage_units(collection):
    collection.add(
        ids=[u[0] for u in UNITS],
        documents=[u[1] for u in UNITS],
        metadatas=[u[2] for u in UNITS],
    )


def _fake_dense(monkeypatch, collection, unit_ids):
    """Pin the dense ranking to `unit_ids`, in that order."""
    by_id = {u[0]: u for u in UNITS}
    picked = [by_id[i] for i in unit_ids]
    fake = {
        "ids": [[u[0] for u in picked]],
        "documents": [[u[1] for u in picked]],
        "metadatas": [[u[2] for u in picked]],
        "distances": [[0.2 + 0.1 * i for i in range(len(picked))]],
    }
    monkeypatch.setattr(type(collection), "query", lambda self, **kw: fake)


@pytest.fixture
def section_client(client, test_collection, tmp_path, monkeypatch):
    """Three Kraken units under one section tree, plus a bulky Dragon
    sibling so the section root is the Kraken and not all of Monsters.

    `tmp_path` is the client's data dir, so the parents land where the
    app reads them. Dense returns Actions first, Legendary Actions
    second — two hits inside the same section."""
    _stage_units(test_collection)
    upsert_parents(tmp_path, SOURCE, [
        _parent("p-d", "Monsters > Dragon", "s_d", "s_m/s_d", DRAGON_TEXT),
        _parent("p-k", "Monsters > Kraken", "s_k", "s_m/s_k"),
        _parent("p-ka", "Monsters > Kraken > Actions", "s_ka", "s_m/s_k/s_ka"),
        _parent("p-kl", "Monsters > Kraken > Legendary Actions",
                "s_kl", "s_m/s_k/s_kl"),
    ])
    _fake_dense(monkeypatch, test_collection, ["u-ka", "u-kl"])
    return client


@pytest.fixture
def section_client_legacy(client, test_collection, tmp_path, monkeypatch):
    """An index predating the section columns: parents carry no
    section_id/section_path and the units' metadata has section_path "".

    Each parent covers exactly its unit's page, so nothing widens the span
    — the hit keeps its printed page labels."""
    legacy_units = [
        (uid, doc, {**meta, "section_id": "", "section_path": ""})
        for uid, doc, meta in UNITS
    ]
    test_collection.add(
        ids=[u[0] for u in legacy_units],
        documents=[u[1] for u in legacy_units],
        metadatas=[u[2] for u in legacy_units],
    )
    upsert_parents(tmp_path, SOURCE, [
        _parent("p-k", "Monsters > Kraken", None, None, pages=(10, 10)),
        _parent("p-ka", "Monsters > Kraken > Actions", None, None, pages=(10, 10)),
        _parent("p-kl", "Monsters > Kraken > Legendary Actions", None, None,
                pages=(10, 10)),
    ])
    picked = [legacy_units[1], legacy_units[2]]
    fake = {
        "ids": [[u[0] for u in picked]],
        "documents": [[u[1] for u in picked]],
        "metadatas": [[u[2] for u in picked]],
        "distances": [[0.2, 0.3]],
    }
    monkeypatch.setattr(type(test_collection), "query", lambda self, **kw: fake)
    return client


@pytest.fixture
def section_client_no_parents(client, test_collection, tmp_path, monkeypatch):
    """Units in Chroma whose parents rows are gone (cleared store, or a
    half-finished reindex): every subtree measures 0 chars, so nothing may
    be allowed to "fit" at depth 1."""
    _stage_units(test_collection)
    _fake_dense(monkeypatch, test_collection, ["u-ka", "u-kl"])
    return client


@pytest.fixture
def section_client_three_sections(client, test_collection, tmp_path, monkeypatch):
    """The same three units, but each in a section of its own — a pool the
    dedupe loop can either satisfy or drain, which is what `exhausted`
    reports."""
    units = [
        (uid, doc, {**meta, "section_id": sid, "section_path": sid})
        for (uid, doc, meta), sid in zip(UNITS, ["s_a", "s_b", "s_c"])
    ]
    test_collection.add(
        ids=[u[0] for u in units],
        documents=[u[1] for u in units],
        metadatas=[u[2] for u in units],
    )
    upsert_parents(tmp_path, SOURCE, [
        _parent(m["parent_id"], m["section_heading"], m["section_id"],
                m["section_path"])
        for _, _, m in units
    ])
    fake = {
        "ids": [[u[0] for u in units]],
        "documents": [[u[1] for u in units]],
        "metadatas": [[u[2] for u in units]],
        "distances": [[0.2, 0.3, 0.4]],
    }
    monkeypatch.setattr(type(test_collection), "query", lambda self, **kw: fake)
    return client


def _search(client, **overrides):
    """POST /api/search with every pipeline knob pinned."""
    payload = {
        "query": "kraken",
        "n_results": 5,
        "rerank": False,
        "hybrid": False,
        "spell_correction": False,
        "variant_expansion": False,
        **overrides,
    }
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_hit_returns_the_whole_section_and_the_matched_unit(section_client):
    r = _search(section_client, query="kraken ink cloud", rerank=False)["results"]
    assert r[0]["section_id"] == "s_k"
    assert r[0]["section_path"] == "s_m/s_k"
    assert "AC 18" in r[0]["text"] and "Ink cloud" in r[0]["text"]     # the section, not the parent
    assert r[0]["matched_text"] == "Tentacle attack text"               # the unit that hit
    assert r[0]["chunk_text"].startswith("Tentacle")                    # its parent
    assert r[0]["section_heading"] == "Monsters > Kraken"
    assert (r[0]["page_start"], r[0]["page_end"]) == (10, 11)           # the section's span


def test_two_hits_in_one_section_dedupe_to_one_result(section_client):
    r = _search(section_client, query="kraken", rerank=False)["results"]
    assert [x["section_id"] for x in r].count("s_k") == 1


def test_legacy_rows_without_section_path_still_return(section_client_legacy):
    r = _search(section_client_legacy, query="kraken", rerank=False)["results"]
    assert r and r[0]["section_id"] == "" and r[0]["matched_text"]


def test_the_roots_found_while_deduping_are_handed_to_fetch_sections(
    section_client, monkeypatch
):
    """The dedupe loop already paid for each candidate's root; assembling
    the sections must not compute them a second time."""
    import server

    seen: dict = {}
    real = server.fetch_sections

    def spy(data_dir, hits, **kwargs):
        seen["hits"] = hits
        seen.update(kwargs)
        return real(data_dir, hits, **kwargs)

    monkeypatch.setattr(server, "fetch_sections", spy)
    assert _search(section_client, query="kraken")["results"]
    assert all(pid in seen["roots"] for pid, _, _ in seen["hits"])
    assert seen["roots"]["p-ka"] == "s_m/s_k"
    # One shared aggregate memo across the request's candidates.
    assert (SOURCE, "s_m") in seen["cache"]


def test_units_whose_parents_are_missing_stay_one_result_each(
    section_client_no_parents
):
    """A source with no parent rows measures 0 chars at every depth. If
    that counted as "fits", both hits would share the depth-1 key and the
    whole book would answer with a single result."""
    r = _search(section_client_no_parents, query="kraken")["results"]
    assert len(r) == 2
    assert [x["matched_text"] for x in r] == [
        "Tentacle attack text", "Ink cloud text"]
    assert [x["text"] for x in r] == ["Tentacle attack text", "Ink cloud text"]


def test_a_widened_span_drops_the_matched_units_page_labels(section_client):
    """`page_start`/`page_end` are now the section's. Keeping the unit's
    printed labels would cite "p.326 (PDF pp.10-11)"."""
    r = _search(section_client, query="kraken")["results"]
    assert (r[0]["page_start"], r[0]["page_end"]) == (10, 11)
    assert r[0]["page_label_start"] == "" and r[0]["page_label_end"] == ""


def test_a_hit_whose_span_did_not_widen_keeps_its_page_labels(
    section_client_legacy
):
    r = _search(section_client_legacy, query="kraken")["results"]
    assert (r[0]["page_start"], r[0]["page_end"]) == (10, 10)
    assert r[0]["page_label_start"] == "326" and r[0]["page_label_end"] == "326"


def test_cross_edition_twin_collapses_into_also_in(client, test_collection, monkeypatch):
    """Two editions of the same rule (identical matched_text, same leaf
    title, different files) are one result with the twin in `also_in`
    (roadmap 2.3) — no parents/sections needed, same as the no-parents
    fixture above."""
    twins = [
        ("u-51", "You create three glowing darts of magical force.",
         {"parent_id": "p-51", "section_id": "s_51", "section_path": "",
          "filename": "SRD_5.1.pdf", "source": "/l/SRD_5.1.pdf",
          "game_system": "5e", "section_heading": "Spells > Magic Missile",
          "page_start": 1, "page_end": 1,
          "page_label_start": "", "page_label_end": ""}),
        ("u-521", "You create three glowing darts of magical force.",
         {"parent_id": "p-521", "section_id": "s_521", "section_path": "",
          "filename": "SRD_5.2.1.pdf", "source": "/l/SRD_5.2.1.pdf",
          "game_system": "5e", "section_heading": "Spells > Magic Missile",
          "page_start": 1, "page_end": 1,
          "page_label_start": "", "page_label_end": ""}),
    ]
    test_collection.add(
        ids=[u[0] for u in twins],
        documents=[u[1] for u in twins],
        metadatas=[u[2] for u in twins],
    )
    fake = {
        "ids": [[u[0] for u in twins]],
        "documents": [[u[1] for u in twins]],
        "metadatas": [[u[2] for u in twins]],
        "distances": [[0.1, 0.2]],
    }
    monkeypatch.setattr(type(test_collection), "query", lambda self, **kw: fake)

    r = _search(client, query="magic missile", rerank=False)["results"]
    assert len(r) == 1
    assert len(r[0]["also_in"]) == 1
    assert r[0]["also_in"][0]["filename"] == "SRD_5.2.1.pdf"


# ---------------------------------------------------------------------------
# `exhausted` — the paging invariant the frontend needs (roadmap 2.x)
# ---------------------------------------------------------------------------

def test_exhausted_is_false_while_the_pool_still_has_sections(
    section_client_three_sections
):
    """Three sections, two asked for: a bigger request would find more, so
    the frontend must keep scroll-load alive even if dedupe, near-dup
    collapse or packing shortened the returned list."""
    data = _search(section_client_three_sections, n_results=2)
    assert data["exhausted"] is False


def test_exhausted_is_true_when_the_pool_runs_dry(section_client_three_sections):
    data = _search(section_client_three_sections, n_results=5)
    assert data["exhausted"] is True


def test_exhausted_is_true_when_a_filter_returns_nothing(section_client):
    """The early returns are ends of the road too — no amount of paging
    turns an unresolvable filter into results."""
    data = _search(section_client, game_system="Not A Real System")
    assert data["results"] == [] and data["exhausted"] is True

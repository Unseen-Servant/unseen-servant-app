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
        "page_label_start": "",
        "page_label_end": "",
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
            section_path: str | None, text: str | None = None) -> ParentDoc:
    return ParentDoc(
        parent_id=pid,
        text=text if text is not None else PARENT_TEXTS[pid],
        section_heading=heading,
        chunk_type="prose",
        source_pdf=SOURCE,
        page_start=10,
        page_end=11,
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
    section_id/section_path and the units' metadata has section_path ""."""
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
        _parent("p-k", "Monsters > Kraken", None, None),
        _parent("p-ka", "Monsters > Kraken > Actions", None, None),
        _parent("p-kl", "Monsters > Kraken > Legendary Actions", None, None),
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
    assert "AC 18" in r[0]["text"] and "Ink cloud" in r[0]["text"]     # the section, not the parent
    assert r[0]["matched_text"] == "Tentacle attack text"               # the unit that hit
    assert r[0]["chunk_text"].startswith("Tentacle")                    # its parent
    assert r[0]["section_heading"] == "Monsters > Kraken"


def test_two_hits_in_one_section_dedupe_to_one_result(section_client):
    r = _search(section_client, query="kraken", rerank=False)["results"]
    assert [x["section_id"] for x in r].count("s_k") == 1


def test_legacy_rows_without_section_path_still_return(section_client_legacy):
    r = _search(section_client_legacy, query="kraken", rerank=False)["results"]
    assert r and r[0]["section_id"] == "" and r[0]["matched_text"]

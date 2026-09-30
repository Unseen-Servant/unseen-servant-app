"""/api/search returns assembled sections (roadmap 2.1, server side).

A hit is answered with the whole section the matched unit belongs to —
the root chosen by `parents_store.section_root_for` — deduped by that
root rather than by parent_id, with the unit that actually matched
(`matched_text`) and its own parent (`chunk_text`) kept alongside.

The fixtures stage units and their parents directly in the library store,
then pin the dense ranking with a fake `store.knn` — the same
deterministic setup as `test_search_hybrid.py`.
"""

import pytest

from legend_lore.granularity import EmbedUnit, ParentDoc
from legend_lore.service import pack_results
from tests.conftest import seed_book

SOURCE = "/corpus/monsters.pdf"

# A sibling monster large enough to push the "Monsters" subtree past
# SECTION_CAP, so the section root for a Kraken hit is `s_m/s_k` (the
# Kraken) rather than the whole bestiary.
DRAGON_TEXT = "Dragon lore. " * 500


def _unit(ordinal: int, text: str, parent_id: str, section_id: str | None,
          section_path: str | None, heading: str, source: str = SOURCE) -> EmbedUnit:
    return EmbedUnit(
        chunk_id=f"c{ordinal}", text=text, parent_id=parent_id,
        chunk_type="prose", section_heading=heading, source_pdf=source,
        page_start=10, page_end=10, ordinal=ordinal,
        section_id=section_id, section_path=section_path,
    )


# Front matter puts the printed number well ahead of the physical one, as
# in a real book.
PAGE_LABELS = {10: "326"}

UNITS = [
    _unit(0, "Kraken overview text", "p-k", "s_k", "s_m/s_k", "Monsters > Kraken"),
    _unit(1, "Tentacle attack text", "p-ka", "s_ka", "s_m/s_k/s_ka",
          "Monsters > Kraken > Actions"),
    _unit(2, "Ink cloud text", "p-kl", "s_kl", "s_m/s_k/s_kl",
          "Monsters > Kraken > Legendary Actions"),
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


def _unit_ids(store, path: str = SOURCE) -> list[int]:
    """The store's unit ids for a book, in ordinal order."""
    return [r[0] for r in store.conn().execute(
        "SELECT u.id FROM units u JOIN documents d ON d.id = u.document_id "
        "WHERE d.path = ? ORDER BY u.ordinal", (path,))]


def _fake_dense(monkeypatch, store, pinned):
    """Pin the dense ranking to `pinned` — (path, ordinal) pairs, in that
    order — with increasing distances. Resolved on each call so the ids
    track whatever is in the store."""
    def knn(vector, k, doc_ids=None):
        return [
            (_unit_ids(store, path)[ordinal], 0.2 + 0.1 * i)
            for i, (path, ordinal) in enumerate(pinned)
        ]
    monkeypatch.setattr(store, "knn", knn)


def _seed(store, embed_fn, units, parents=()):
    seed_book(store, embed_fn, SOURCE, units, parents=parents,
              game_system="OSR", page_labels=PAGE_LABELS)


@pytest.fixture
def section_client(client, test_store, test_embed_fn, monkeypatch):
    """Three Kraken units under one section tree, plus a bulky Dragon
    sibling so the section root is the Kraken and not all of Monsters.

    Dense returns Actions first, Legendary Actions second — two hits
    inside the same section."""
    _seed(test_store, test_embed_fn, UNITS, [
        _parent("p-d", "Monsters > Dragon", "s_d", "s_m/s_d", DRAGON_TEXT),
        _parent("p-k", "Monsters > Kraken", "s_k", "s_m/s_k"),
        _parent("p-ka", "Monsters > Kraken > Actions", "s_ka", "s_m/s_k/s_ka"),
        _parent("p-kl", "Monsters > Kraken > Legendary Actions",
                "s_kl", "s_m/s_k/s_kl"),
    ])
    _fake_dense(monkeypatch, test_store, [(SOURCE, 1), (SOURCE, 2)])
    return client


@pytest.fixture
def section_client_legacy(client, test_store, test_embed_fn, monkeypatch):
    """An index predating the section columns: parents carry no
    section_id/section_path and neither do the units.

    Each parent covers exactly its unit's page, so nothing widens the span
    — the hit keeps its printed page labels."""
    legacy_units = [
        _unit(u.ordinal, u.text, u.parent_id, None, None, u.section_heading)
        for u in UNITS
    ]
    _seed(test_store, test_embed_fn, legacy_units, [
        _parent("p-k", "Monsters > Kraken", None, None, pages=(10, 10)),
        _parent("p-ka", "Monsters > Kraken > Actions", None, None, pages=(10, 10)),
        _parent("p-kl", "Monsters > Kraken > Legendary Actions", None, None,
                pages=(10, 10)),
    ])
    _fake_dense(monkeypatch, test_store, [(SOURCE, 1), (SOURCE, 2)])
    return client


@pytest.fixture
def section_client_no_parents(client, test_store, test_embed_fn, monkeypatch):
    """Units whose book has no parents rows: every subtree measures 0
    chars, so nothing may be allowed to "fit" at depth 1."""
    _seed(test_store, test_embed_fn, UNITS)
    _fake_dense(monkeypatch, test_store, [(SOURCE, 1), (SOURCE, 2)])
    return client


@pytest.fixture
def section_client_three_sections(client, test_store, test_embed_fn, monkeypatch):
    """The same three units, but each in a section of its own — a pool the
    dedupe loop can either satisfy or drain, which is what `exhausted`
    reports."""
    units = [
        _unit(u.ordinal, u.text, u.parent_id, sid, sid, u.section_heading)
        for u, sid in zip(UNITS, ["s_a", "s_b", "s_c"])
    ]
    _seed(test_store, test_embed_fn, units, [
        _parent(u.parent_id, u.section_heading, u.section_id, u.section_path)
        for u in units
    ])
    _fake_dense(monkeypatch, test_store, [(SOURCE, 0), (SOURCE, 1), (SOURCE, 2)])
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
    from legend_lore import service

    seen: dict = {}
    real = service.fetch_sections

    def spy(store, hits, **kwargs):
        seen["hits"] = hits
        seen.update(kwargs)
        return real(store, hits, **kwargs)

    monkeypatch.setattr(service, "fetch_sections", spy)
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


def test_cross_edition_twin_collapses_into_also_in(
    client, test_store, test_embed_fn, monkeypatch
):
    """Two editions of the same rule (identical matched_text, same leaf
    title, different files) are one result with the twin in `also_in`
    (roadmap 2.3) — no parents/sections needed, same as the no-parents
    fixture above."""
    twins = [("/l/SRD_5.1.pdf", "p-51", "s_51"),
             ("/l/SRD_5.2.1.pdf", "p-521", "s_521")]
    for path, pid, sid in twins:
        unit = EmbedUnit(
            chunk_id="c0", text="You create three glowing darts of magical force.",
            parent_id=pid, chunk_type="prose",
            section_heading="Spells > Magic Missile", source_pdf=path,
            page_start=1, page_end=1, ordinal=0, section_id=sid, section_path=None,
        )
        seed_book(test_store, test_embed_fn, path, [unit], game_system="5e")
    _fake_dense(monkeypatch, test_store, [(p, 0) for p, _, _ in twins])

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


# ---------------------------------------------------------------------------
# `max_context_chars` packer (roadmap 2.2, API side).
#
# `pack_results` walks the formatted results in rank order, accumulating
# `len(text) + len(section_heading)` under a caller-supplied budget. The
# first result that doesn't fit is cut down to its matched unit (if that
# narrower text fits) and ends the list; everything already accepted
# keeps its full section text. `None` means unlimited — every result
# passes through unmodified except for the added `truncated: False` flag.
# ---------------------------------------------------------------------------


def _r(text, matched, heading="H"):
    return {"text": text, "matched_text": matched, "section_heading": heading}


def test_pack_keeps_everything_when_unbudgeted():
    out = pack_results([_r("a" * 100, "a"), _r("b" * 100, "b")], None)
    assert [x["truncated"] for x in out] == [False, False]


def test_pack_truncates_the_last_result_to_its_matched_unit_and_stops():
    out = pack_results([_r("a" * 100, "aa"), _r("b" * 100, "bb"), _r("c" * 100, "cc")], 150)
    assert len(out) == 2
    assert out[0]["truncated"] is False and out[1]["truncated"] is True and out[1]["text"] == "bb"


def test_pack_drops_a_result_whose_matched_unit_does_not_fit_either():
    out = pack_results([_r("a" * 100, "aa"), _r("b" * 100, "b" * 60)], 110)
    assert len(out) == 1


def test_search_honours_max_context_chars(section_client):
    # The section fixture's single Kraken section (query="kraken", the
    # dedupe target of test_search_sections.py) runs ~181 chars
    # (text + heading), under the brief's suggested budget of 200 — a
    # budget that size would never force truncation here. 100 sits
    # between that full-section cost and the matched-unit fallback cost
    # (~38 chars), so the packer must cut it down instead of passing it
    # through whole.
    body = _search(section_client, query="kraken", rerank=False, max_context_chars=100)
    total = sum(len(r["text"]) + len(r["section_heading"]) for r in body["results"])
    assert total <= 100 and any(r["truncated"] for r in body["results"])

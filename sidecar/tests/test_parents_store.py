"""Unit tests for parents_store — parent and section reads over the library store."""

import pytest

from legend_lore.granularity import EmbedUnit, ParentDoc
from legend_lore.library_store import LibraryStore
from legend_lore.parents_store import (
    fetch_parents,
    fetch_parents_extended,
    SECTION_CAP,
    _heading_at_depth,
    _prefix_range,
    assemble_section,
    fetch_section_by_id,
    fetch_sections,
    section_root_for,
)


@pytest.fixture
def store(tmp_path):
    s = LibraryStore.open(tmp_path / "library.sqlite3", "test-model", 2)
    yield s
    s.close()


def upsert_parents(store, path: str, parents: list[ParentDoc]) -> None:
    """Index a book that has parents only (no units) — what these reads need."""
    store.replace_document(path, "unknown", (), [], [], [], parents)


def count_parents(store) -> int:
    return store.conn().execute("SELECT count(*) FROM parents").fetchone()[0]


def _p(
    pid: str,
    source_pdf: str,
    text: str,
    section: str | None,
    page_start: int = 1,
    page_end: int = 1,
    chunk_type: str = "prose",
    sid: str | None = None,
    path: str | None = None,
) -> ParentDoc:
    return ParentDoc(
        parent_id=pid,
        text=text,
        section_heading=section,
        chunk_type=chunk_type,
        source_pdf=source_pdf,
        page_start=page_start,
        page_end=page_end,
        section_id=sid,
        section_path=path,
    )


def _parent(pid: str, source_pdf: str = "test.pdf", text: str = "body") -> ParentDoc:
    return ParentDoc(
        parent_id=pid,
        text=text,
        section_heading="Section",
        chunk_type="prose",
        source_pdf=source_pdf,
        page_start=1,
        page_end=2,
    )


def test_upsert_and_fetch_roundtrip(store):
    parents = [_parent("p_1"), _parent("p_2")]
    upsert_parents(store, "/lib/test.pdf", parents)
    fetched = fetch_parents(store, ["p_1", "p_2"])
    assert set(fetched.keys()) == {"p_1", "p_2"}
    assert fetched["p_1"].text == "body"
    assert fetched["p_1"].section_heading == "Section"
    assert fetched["p_1"].page_start == 1
    assert fetched["p_1"].page_end == 2


def test_fetch_missing_id_silently_absent(store):
    upsert_parents(store, "/lib/x.pdf", [_parent("p_only")])
    fetched = fetch_parents(store, ["p_only", "p_missing"])
    assert "p_only" in fetched
    assert "p_missing" not in fetched


def test_upsert_replaces_old_parents_for_source(store):
    """Re-indexing a source must not leave orphans even when parent_ids change."""
    upsert_parents(store, "/lib/x.pdf", [_parent("p_old_1"), _parent("p_old_2")])
    assert count_parents(store) == 2
    upsert_parents(store, "/lib/x.pdf", [_parent("p_new_1")])
    assert count_parents(store) == 1
    assert "p_new_1" in fetch_parents(store, ["p_new_1"])
    assert fetch_parents(store, ["p_old_1"]) == {}


def test_upsert_does_not_touch_other_sources(store):
    upsert_parents(store, "/lib/a.pdf", [_parent("p_a", source_pdf="a.pdf")])
    upsert_parents(store, "/lib/b.pdf", [_parent("p_b", source_pdf="b.pdf")])
    upsert_parents(store, "/lib/a.pdf", [_parent("p_a2", source_pdf="a.pdf")])
    assert "p_b" in fetch_parents(store, ["p_b"])
    assert "p_a" not in fetch_parents(store, ["p_a"])
    assert "p_a2" in fetch_parents(store, ["p_a2"])


def test_delete_document_drops_only_its_parents(store):
    upsert_parents(store, "/lib/a.pdf", [_parent("p_a"), _parent("p_a2")])
    upsert_parents(store, "/lib/b.pdf", [_parent("p_b")])
    store.delete_document("/lib/a.pdf")
    assert count_parents(store) == 1
    assert "p_b" in fetch_parents(store, ["p_b"])


def test_fetch_with_empty_id_list(store):
    upsert_parents(store, "/lib/x.pdf", [_parent("p_x")])
    assert fetch_parents(store, []) == {}


# ---------------------------------------------------------------------------
# fetch_parents_extended — section-aware result expansion
# ---------------------------------------------------------------------------


def test_extended_single_parent_returns_unchanged(store):
    """A section that fits in a single parent returns its text unchanged."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "before", "Other Section"),
        _p("p_b", "/lib/x.pdf", "alone", "My Section"),
        _p("p_c", "/lib/x.pdf", "after", "Different Section"),
    ])
    fetched = fetch_parents_extended(store, ["p_b"])
    assert fetched["p_b"].text == "alone"


def test_extended_stitches_split_section_forward(store):
    """Two parents with same source + section + adjacent rowid stitch."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "first half", "Combat", page_start=1, page_end=2),
        _p("p_b", "/lib/x.pdf", "second half", "Combat", page_start=2, page_end=3),
        _p("p_c", "/lib/x.pdf", "next", "Movement", page_start=3, page_end=4),
    ])
    fetched = fetch_parents_extended(store, ["p_a"])
    assert fetched["p_a"].text == "first half\n\nsecond half"
    assert fetched["p_a"].page_start == 1
    assert fetched["p_a"].page_end == 3


def test_extended_walks_both_directions(store):
    """Stitches both backward and forward neighbors when budget allows."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "back", "Combat", page_start=1, page_end=1),
        _p("p_b", "/lib/x.pdf", "middle", "Combat", page_start=2, page_end=2),
        _p("p_c", "/lib/x.pdf", "forward", "Combat", page_start=3, page_end=3),
        _p("p_d", "/lib/x.pdf", "next", "Movement", page_start=4, page_end=4),
    ])
    fetched = fetch_parents_extended(store, ["p_b"])
    assert fetched["p_b"].text == "back\n\nmiddle\n\nforward"
    assert fetched["p_b"].page_start == 1
    assert fetched["p_b"].page_end == 3


def test_extended_stops_at_section_boundary(store):
    """Stitching does not cross a section_heading change."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "before", "Other"),
        _p("p_b", "/lib/x.pdf", "target", "Combat"),
        _p("p_c", "/lib/x.pdf", "different", "Movement"),
    ])
    fetched = fetch_parents_extended(store, ["p_b"])
    assert fetched["p_b"].text == "target"


def test_extended_skips_neighbor_over_budget(store):
    """A neighbor too large for the budget is skipped (no truncation)."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "x" * 100, "Combat"),
        _p("p_b", "/lib/x.pdf", "target", "Combat"),
    ])
    fetched = fetch_parents_extended(store, ["p_b"], max_extra_chars=50)
    assert fetched["p_b"].text == "target"


def test_extended_does_not_cross_sources(store):
    """Adjacent rowids in different sources should never stitch."""
    upsert_parents(store, "/lib/a.pdf", [_p("p_a", "/lib/a.pdf", "in a", "Combat")])
    upsert_parents(store, "/lib/b.pdf", [_p("p_b", "/lib/b.pdf", "in b", "Combat")])
    assert fetch_parents_extended(store, ["p_a"])["p_a"].text == "in a"
    assert fetch_parents_extended(store, ["p_b"])["p_b"].text == "in b"


def test_extended_stitches_null_section_siblings(store):
    """Adjacent parents with section_heading=None stitch (same 'no-heading' run)."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "first", None),
        _p("p_b", "/lib/x.pdf", "second", None),
    ])
    fetched = fetch_parents_extended(store, ["p_a"])
    assert fetched["p_a"].text == "first\n\nsecond"


def test_extended_batch_returns_all(store):
    """Batch fetch handles multiple parent_ids in one call."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "alpha", "S1"),
        _p("p_b", "/lib/x.pdf", "beta", "S2"),
    ])
    fetched = fetch_parents_extended(store, ["p_a", "p_b"])
    assert set(fetched.keys()) == {"p_a", "p_b"}


def test_extended_missing_id_silently_absent(store):
    upsert_parents(store, "/lib/x.pdf", [_p("p_only", "/lib/x.pdf", "only", "S")])
    fetched = fetch_parents_extended(store, ["p_only", "p_missing"])
    assert "p_only" in fetched
    assert "p_missing" not in fetched


def test_extended_empty_id_list(store):
    upsert_parents(store, "/lib/x.pdf", [_p("p_x", "/lib/x.pdf", "x", "S")])
    assert fetch_parents_extended(store, []) == {}


def test_extended_stops_partway_when_third_neighbor_breaks_section(store):
    """Section split into 3 parents, last one belongs to a different section.
    Expansion includes the first two but stops at the boundary."""
    upsert_parents(store, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "a-text", "Combat", page_start=1, page_end=1),
        _p("p_b", "/lib/x.pdf", "b-text", "Combat", page_start=2, page_end=2),
        _p("p_c", "/lib/x.pdf", "c-text", "Movement", page_start=3, page_end=3),
    ])
    fetched = fetch_parents_extended(store, ["p_a"])
    assert fetched["p_a"].text == "a-text\n\nb-text"
    assert fetched["p_a"].page_end == 2


# ---------------------------------------------------------------------------
# section_id stitching (roadmap 1.3)
# ---------------------------------------------------------------------------


def test_extended_stops_at_section_id_boundary_even_with_equal_headings(store):
    upsert_parents(store, "x.pdf", [
        _p("p1", "x.pdf", "a" * 10, "Actions", sid="s_k"),
        _p("p2", "x.pdf", "b" * 10, "Actions", sid="s_m"),
    ])
    got = fetch_parents_extended(store, ["p1"])
    assert got["p1"].text == "a" * 10


# ---------------------------------------------------------------------------
# Rename — parents and FTS rows follow the book (roadmap 1.6, S5)
# ---------------------------------------------------------------------------


def test_rename_moves_parents_and_lexical_rows_with_the_book(store):
    unit = EmbedUnit(chunk_id="c", text="more", parent_id="p1", chunk_type="prose",
                     section_heading=None, source_pdf="/old/a.pdf",
                     page_start=1, page_end=1, ordinal=1)
    store.replace_document("/old/a.pdf", "OSR", (), [unit], ["more"],
                           [[1.0, 0.0]], [_parent("p1", "/old/a.pdf")])
    store.rename_document("/old/a.pdf", "/new/b.pdf")
    assert store.scope_document_ids(filename="a.pdf") == []
    new_doc = store.scope_document_ids(filename="b.pdf")
    assert len(store.fts('"more"', 5, new_doc)) == 1
    assert fetch_parents(store, ["p1"])["p1"].source_pdf == "/new/b.pdf"


# ---------------------------------------------------------------------------
# Section assembly by section_path prefix (roadmap 2.1)
# ---------------------------------------------------------------------------

# A monster chapter: Monsters (s_m) > Kraken (s_k) > {Actions (s_ka), Legendary (s_kl)}; Medusa (s_d) > Actions (s_da)
def _monster_tree(store):
    rows = [
        _p("p_intro", "x.pdf", "Monsters intro " * 20, "Monsters", 1, 1, sid="s_m", path="s_m"),
        _p("p_kra", "x.pdf", "Kraken AC 18 HP 472 " * 30, "Monsters > Kraken", 2, 2, sid="s_k", path="s_m/s_k"),
        _p("p_kra_act", "x.pdf", "Tentacle attack " * 30, "Monsters > Kraken > Actions", 2, 3, sid="s_ka", path="s_m/s_k/s_ka"),
        _p("p_kra_leg", "x.pdf", "Ink cloud legendary " * 30, "Monsters > Kraken > Legendary Actions", 3, 3, sid="s_kl", path="s_m/s_k/s_kl"),
        _p("p_med", "x.pdf", "Medusa AC 15 " * 30, "Monsters > Medusa", 4, 4, sid="s_d", path="s_m/s_d"),
        _p("p_med_act", "x.pdf", "Petrifying gaze " * 30, "Monsters > Medusa > Actions", 4, 4, sid="s_da", path="s_m/s_d/s_da"),
    ]
    upsert_parents(store, "x.pdf", rows)
    return rows


def test_prefix_range_covers_self_and_descendants_only():
    lo, hi = _prefix_range("s_m/s_k")
    assert lo == "s_m/s_k" and hi == "s_m/s_k0"
    assert lo <= "s_m/s_k" < hi and lo <= "s_m/s_k/s_ka" < hi
    assert not (lo <= "s_m/s_d" < hi) and not (lo <= "s_m/s_kz" < hi)   # 'z' > '0'


def test_section_root_is_the_shallowest_ancestor_that_fits(store):
    _monster_tree(store)
    conn = store.conn()
    # Kraken subtree is 1 684 chars, fits; Monsters subtree is 2 860, also fits under 6 000 → Monsters is chosen …
    assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cap=SECTION_CAP) == "s_m"
    # … but with a 2 000-char cap the whole chapter (2 860) does not fit and Kraken (1 684) is the root.
    assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cap=2000) == "s_m/s_k"
    # A leaf larger than the cap (480 > 100) stays the leaf.
    assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cap=100) == "s_m/s_k/s_ka"


def test_heading_at_depth_cuts_the_breadcrumb():
    assert _heading_at_depth("Monsters > Kraken > Actions", 2) == "Monsters > Kraken"
    assert _heading_at_depth("Monsters", 3) == "Monsters"
    assert _heading_at_depth(None, 2) is None


def test_assemble_section_returns_the_subtree_in_document_order(store):
    _monster_tree(store)
    conn = store.conn()
    doc = assemble_section(conn, "x.pdf", "s_m/s_k", "p_kra_act", cap=2000)
    assert doc.text.startswith("Kraken AC 18") and "Ink cloud" in doc.text
    assert doc.text.index("Tentacle") < doc.text.index("Ink cloud")
    assert (doc.page_start, doc.page_end) == (2, 3)
    assert doc.section_heading == "Monsters > Kraken"
    assert doc.section_id == "s_k" and doc.windowed is False


def test_assemble_section_heading_truncates_to_root_depth(store):
    """The root is shallower than the first row's own breadcrumb: the
    heading must be cut to the root's depth, not the row's full chain."""
    upsert_parents(store, "z.pdf", [
        _p("p_leaf", "z.pdf", "Leaf text", "Chapter > Sub > Leaf", 1, 1, sid="s_l", path="s_c/s_s/s_l"),
    ])
    conn = store.conn()
    doc = assemble_section(conn, "z.pdf", "s_c/s_s", "p_leaf", cap=SECTION_CAP)
    assert doc.section_heading == "Chapter > Sub"


def test_assemble_section_windows_a_leaf_larger_than_the_cap(store):
    rows = [_p(f"p{i}", "y.pdf", f"para{i} " * 40, "Long > Section", 1, 1, sid="s_l", path="s_x/s_l") for i in range(10)]
    upsert_parents(store, "y.pdf", rows)
    conn = store.conn()
    doc = assemble_section(conn, "y.pdf", "s_x/s_l", "p5", cap=900)
    assert doc.windowed is True
    assert "para5" in doc.text and len(doc.text) <= 900
    assert "para4" in doc.text or "para6" in doc.text          # grows outward from the match
    assert "para0" not in doc.text and "para9" not in doc.text


def test_fetch_sections_falls_back_to_the_heading_walk_for_legacy_rows(store):
    upsert_parents(store, "old.pdf", [_p("a", "old.pdf", "one", "H"), _p("b", "old.pdf", "two", "H")])
    got = fetch_sections(store, [("a", None, "old.pdf")])
    assert got["a"].text == "one\n\ntwo" and got["a"].root_path == ""


def test_fetch_sections_batches_and_keys_by_parent_id(store):
    _monster_tree(store)
    got = fetch_sections(store, [("p_kra_act", "s_m/s_k/s_ka", "x.pdf"), ("p_med", "s_m/s_d", "x.pdf")])
    assert set(got) == {"p_kra_act", "p_med"}
    assert got["p_kra_act"].root_path == got["p_med"].root_path == "s_m"   # both fit under the chapter at 6 000


def _count_aggregates(conn) -> list[str]:
    """Collect the subtree-size aggregates SQLite actually runs."""
    sql: list[str] = []
    conn.set_trace_callback(
        lambda s: sql.append(s) if "SUM(LENGTH(text))" in s else None)
    return sql


def test_section_root_for_memoises_the_subtree_aggregates(store):
    """The depth-1 aggregate re-sums the whole chapter's text; candidates
    from one chapter must pay for it once per request, not once each."""
    _monster_tree(store)
    conn = store.conn()
    sql = _count_aggregates(conn)
    assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka") == "s_m"
    assert section_root_for(conn, "x.pdf", "s_m/s_d/s_da") == "s_m"
    assert len(sql) == 2                      # uncached: one each

    sql.clear()
    cache = {}
    assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cache=cache) == "s_m"
    assert section_root_for(conn, "x.pdf", "s_m/s_d/s_da", cache=cache) == "s_m"
    assert len(sql) == 1                      # the second call is all cache
    conn.set_trace_callback(None)


def test_section_root_for_is_none_when_the_source_has_no_parents(store):
    """An empty subtree measures 0 chars and would otherwise "fit" at
    depth 1, collapsing every hit in the book onto one root."""
    _monster_tree(store)
    conn = store.conn()
    assert section_root_for(conn, "gone.pdf", "s_m/s_k/s_ka") is None
    assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka") == "s_m"


def test_fetch_sections_omits_a_hit_whose_source_has_no_parents(store):
    _monster_tree(store)
    assert fetch_sections(store, [("ghost", "s_m/s_k", "gone.pdf")]) == {}


def test_fetch_sections_uses_a_root_the_caller_already_computed(store):
    """The search path picks each hit's root while deduping and hands it
    over; the assembly must take it rather than recompute (which would
    return the whole chapter here)."""
    _monster_tree(store)
    got = fetch_sections(store, [("p_kra_act", "s_m/s_k/s_ka", "x.pdf")],
                         roots={"p_kra_act": "s_m/s_k"})
    assert got["p_kra_act"].root_path == "s_m/s_k"
    assert "Medusa" not in got["p_kra_act"].text


# ---------------------------------------------------------------------------
# fetch_section_by_id — resolve an advertised id, row of its own or not
# ---------------------------------------------------------------------------

def test_fetch_section_by_id_assembles_a_section_that_owns_a_row(store):
    _monster_tree(store)
    doc = fetch_section_by_id(store, "s_k")
    assert doc is not None
    assert doc.section_id == "s_k" and doc.root_path == "s_m/s_k"
    assert "Ink cloud" in doc.text and "Medusa" not in doc.text


def test_fetch_section_by_id_resolves_a_container_with_no_row_of_its_own(store):
    """A heading immediately followed by a sub-heading owns no chunk, so
    no parents row carries its section_id — yet `section_root_for` picks
    it as the section root and search advertises that id. Resolution has
    to go through the path segments, not the section_id column."""
    upsert_parents(store, "x.pdf", [
        _p("p_kra", "x.pdf", "Kraken AC 18 " * 5, "Monsters > Kraken",
           2, 2, sid="s_k", path="s_m/s_k"),
        _p("p_med", "x.pdf", "Medusa AC 15 " * 5, "Monsters > Medusa",
           4, 4, sid="s_d", path="s_m/s_d"),
    ])
    doc = fetch_section_by_id(store, "s_m")
    assert doc is not None
    assert doc.section_id == "s_m" and doc.root_path == "s_m"
    assert "Kraken" in doc.text and "Medusa" in doc.text
    assert doc.section_heading == "Monsters"
    assert (doc.page_start, doc.page_end) == (2, 4)


def test_fetch_section_by_id_resolves_a_middle_segment(store):
    """The id can sit anywhere in the path: here `s_k` is a middle
    segment whose own row was never written."""
    upsert_parents(store, "x.pdf", [
        _p("p_act", "x.pdf", "Tentacle attack " * 5,
           "Monsters > Kraken > Actions", 2, 3, sid="s_ka",
           path="s_m/s_k/s_ka"),
        _p("p_leg", "x.pdf", "Ink cloud " * 5,
           "Monsters > Kraken > Legendary Actions", 3, 3, sid="s_kl",
           path="s_m/s_k/s_kl"),
    ])
    doc = fetch_section_by_id(store, "s_k")
    assert doc is not None
    assert doc.root_path == "s_m/s_k" and doc.section_id == "s_k"
    assert "Tentacle" in doc.text and "Ink cloud" in doc.text


def test_fetch_section_by_id_unknown_id_is_none(store):
    _monster_tree(store)
    assert fetch_section_by_id(store, "s_nowhere") is None


def test_count_phrases_counts_units_with_the_adjacent_pair(store):
    texts = ["Thief skills table", "the thief skill of climbing", "skill of this thief"]
    units = [
        EmbedUnit(chunk_id=f"a_{i}", text=t, parent_id="p1", chunk_type="prose",
                  section_heading=None, source_pdf="/lib/a.pdf",
                  page_start=1, page_end=1, ordinal=i)
        for i, t in enumerate(texts)
    ]
    store.replace_document("/lib/a.pdf", "OSR", (), units, texts,
                           [[1.0, 0.0]] * 3, [_parent("p1", "/lib/a.pdf")])
    got = store.count_phrases([("thief", "skill"), ("this", "skill"), ('bad"', "skill")])
    assert got[("thief", "skill")] == 2      # porter stems "skills" → "skill"
    assert got[("this", "skill")] == 0       # not adjacent in that order
    assert got[('bad"', "skill")] == 0       # quotes stripped, no FTS syntax error
    assert store.count_phrases([]) == {}

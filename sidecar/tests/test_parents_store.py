"""Unit tests for parents_store — SQLite-backed parent KV store."""

from granularity import ParentDoc
from parents_store import (
    upsert_parents,
    fetch_parents,
    fetch_parents_extended,
    delete_parents_for_source,
    clear_all_parents,
    count_parents,
    upsert_units_fts,
    search_units_fts,
    delete_units_fts_for_source,
    count_units_fts,
    rename_source,
    update_units_fts_game_system,
    where_to_sql,
    SECTION_CAP,
    _heading_at_depth,
    _prefix_range,
    _txn,
    assemble_section,
    fetch_section_by_id,
    fetch_sections,
    section_root_for,
)


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


def test_upsert_and_fetch_roundtrip(tmp_path):
    parents = [_parent("p_1"), _parent("p_2")]
    upsert_parents(tmp_path, "/lib/test.pdf", parents)
    fetched = fetch_parents(tmp_path, ["p_1", "p_2"])
    assert set(fetched.keys()) == {"p_1", "p_2"}
    assert fetched["p_1"].text == "body"
    assert fetched["p_1"].section_heading == "Section"
    assert fetched["p_1"].page_start == 1
    assert fetched["p_1"].page_end == 2


def test_fetch_missing_id_silently_absent(tmp_path):
    upsert_parents(tmp_path, "/lib/x.pdf", [_parent("p_only")])
    fetched = fetch_parents(tmp_path, ["p_only", "p_missing"])
    assert "p_only" in fetched
    assert "p_missing" not in fetched


def test_upsert_replaces_old_parents_for_source(tmp_path):
    """Re-indexing a source must not leave orphans even when parent_ids change."""
    upsert_parents(tmp_path, "/lib/x.pdf", [_parent("p_old_1"), _parent("p_old_2")])
    assert count_parents(tmp_path) == 2
    upsert_parents(tmp_path, "/lib/x.pdf", [_parent("p_new_1")])
    assert count_parents(tmp_path) == 1
    assert "p_new_1" in fetch_parents(tmp_path, ["p_new_1"])
    assert fetch_parents(tmp_path, ["p_old_1"]) == {}


def test_upsert_does_not_touch_other_sources(tmp_path):
    upsert_parents(tmp_path, "/lib/a.pdf", [_parent("p_a", source_pdf="a.pdf")])
    upsert_parents(tmp_path, "/lib/b.pdf", [_parent("p_b", source_pdf="b.pdf")])
    upsert_parents(tmp_path, "/lib/a.pdf", [_parent("p_a2", source_pdf="a.pdf")])
    assert "p_b" in fetch_parents(tmp_path, ["p_b"])
    assert "p_a" not in fetch_parents(tmp_path, ["p_a"])
    assert "p_a2" in fetch_parents(tmp_path, ["p_a2"])


def test_delete_parents_for_source(tmp_path):
    upsert_parents(tmp_path, "/lib/a.pdf", [_parent("p_a"), _parent("p_a2")])
    upsert_parents(tmp_path, "/lib/b.pdf", [_parent("p_b")])
    deleted = delete_parents_for_source(tmp_path, "/lib/a.pdf")
    assert deleted == 2
    assert count_parents(tmp_path) == 1
    assert "p_b" in fetch_parents(tmp_path, ["p_b"])


def test_clear_all_parents(tmp_path):
    upsert_parents(tmp_path, "/lib/a.pdf", [_parent("p_a")])
    upsert_parents(tmp_path, "/lib/b.pdf", [_parent("p_b")])
    clear_all_parents(tmp_path)
    assert count_parents(tmp_path) == 0


def test_fetch_with_empty_id_list(tmp_path):
    upsert_parents(tmp_path, "/lib/x.pdf", [_parent("p_x")])
    assert fetch_parents(tmp_path, []) == {}


def test_no_data_dir_is_noop(tmp_path):
    """Test path may pass data_dir=None — should not crash."""
    upsert_parents(None, "/lib/x.pdf", [_parent("p_x")])
    assert fetch_parents(None, ["p_x"]) == {}
    assert delete_parents_for_source(None, "/lib/x.pdf") == 0
    assert count_parents(None) == 0
    clear_all_parents(None)


# ---------------------------------------------------------------------------
# fetch_parents_extended — section-aware result expansion
# ---------------------------------------------------------------------------


def test_extended_single_parent_returns_unchanged(tmp_path):
    """A section that fits in a single parent returns its text unchanged."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "before", "Other Section"),
        _p("p_b", "/lib/x.pdf", "alone", "My Section"),
        _p("p_c", "/lib/x.pdf", "after", "Different Section"),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_b"])
    assert fetched["p_b"].text == "alone"


def test_extended_stitches_split_section_forward(tmp_path):
    """Two parents with same source + section + adjacent rowid stitch."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "first half", "Combat", page_start=1, page_end=2),
        _p("p_b", "/lib/x.pdf", "second half", "Combat", page_start=2, page_end=3),
        _p("p_c", "/lib/x.pdf", "next", "Movement", page_start=3, page_end=4),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_a"])
    assert fetched["p_a"].text == "first half\n\nsecond half"
    assert fetched["p_a"].page_start == 1
    assert fetched["p_a"].page_end == 3


def test_extended_walks_both_directions(tmp_path):
    """Stitches both backward and forward neighbors when budget allows."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "back", "Combat", page_start=1, page_end=1),
        _p("p_b", "/lib/x.pdf", "middle", "Combat", page_start=2, page_end=2),
        _p("p_c", "/lib/x.pdf", "forward", "Combat", page_start=3, page_end=3),
        _p("p_d", "/lib/x.pdf", "next", "Movement", page_start=4, page_end=4),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_b"])
    assert fetched["p_b"].text == "back\n\nmiddle\n\nforward"
    assert fetched["p_b"].page_start == 1
    assert fetched["p_b"].page_end == 3


def test_extended_stops_at_section_boundary(tmp_path):
    """Stitching does not cross a section_heading change."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "before", "Other"),
        _p("p_b", "/lib/x.pdf", "target", "Combat"),
        _p("p_c", "/lib/x.pdf", "different", "Movement"),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_b"])
    assert fetched["p_b"].text == "target"


def test_extended_skips_neighbor_over_budget(tmp_path):
    """A neighbor too large for the budget is skipped (no truncation)."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "x" * 100, "Combat"),
        _p("p_b", "/lib/x.pdf", "target", "Combat"),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_b"], max_extra_chars=50)
    assert fetched["p_b"].text == "target"


def test_extended_does_not_cross_sources(tmp_path):
    """Adjacent rowids in different sources should never stitch."""
    upsert_parents(tmp_path, "/lib/a.pdf", [_p("p_a", "/lib/a.pdf", "in a", "Combat")])
    upsert_parents(tmp_path, "/lib/b.pdf", [_p("p_b", "/lib/b.pdf", "in b", "Combat")])
    assert fetch_parents_extended(tmp_path, ["p_a"])["p_a"].text == "in a"
    assert fetch_parents_extended(tmp_path, ["p_b"])["p_b"].text == "in b"


def test_extended_stitches_null_section_siblings(tmp_path):
    """Adjacent parents with section_heading=None stitch (same 'no-heading' run)."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "first", None),
        _p("p_b", "/lib/x.pdf", "second", None),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_a"])
    assert fetched["p_a"].text == "first\n\nsecond"


def test_extended_batch_returns_all(tmp_path):
    """Batch fetch handles multiple parent_ids in one call."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "alpha", "S1"),
        _p("p_b", "/lib/x.pdf", "beta", "S2"),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_a", "p_b"])
    assert set(fetched.keys()) == {"p_a", "p_b"}


def test_extended_missing_id_silently_absent(tmp_path):
    upsert_parents(tmp_path, "/lib/x.pdf", [_p("p_only", "/lib/x.pdf", "only", "S")])
    fetched = fetch_parents_extended(tmp_path, ["p_only", "p_missing"])
    assert "p_only" in fetched
    assert "p_missing" not in fetched


def test_extended_no_data_dir(tmp_path):
    assert fetch_parents_extended(None, ["p_x"]) == {}


def test_extended_empty_id_list(tmp_path):
    upsert_parents(tmp_path, "/lib/x.pdf", [_p("p_x", "/lib/x.pdf", "x", "S")])
    assert fetch_parents_extended(tmp_path, []) == {}


def test_extended_stops_partway_when_third_neighbor_breaks_section(tmp_path):
    """Section split into 3 parents, last one belongs to a different section.
    Expansion includes the first two but stops at the boundary."""
    upsert_parents(tmp_path, "/lib/x.pdf", [
        _p("p_a", "/lib/x.pdf", "a-text", "Combat", page_start=1, page_end=1),
        _p("p_b", "/lib/x.pdf", "b-text", "Combat", page_start=2, page_end=2),
        _p("p_c", "/lib/x.pdf", "c-text", "Movement", page_start=3, page_end=3),
    ])
    fetched = fetch_parents_extended(tmp_path, ["p_a"])
    assert fetched["p_a"].text == "a-text\n\nb-text"
    assert fetched["p_a"].page_end == 2


# ---------------------------------------------------------------------------
# section_id migration + stitching (roadmap 1.3)
# ---------------------------------------------------------------------------


def test_migrate_adds_section_columns_to_an_old_store(tmp_path):
    import sqlite3
    db = tmp_path / "parents.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript("""CREATE TABLE parents (parent_id TEXT PRIMARY KEY, source TEXT NOT NULL,
        text TEXT NOT NULL, section_heading TEXT, page_start INTEGER NOT NULL,
        page_end INTEGER NOT NULL, chunk_type TEXT NOT NULL);""")
    conn.execute("INSERT INTO parents VALUES ('p1','old.pdf','t','H',1,1,'prose')")
    conn.commit(); conn.close()
    got = fetch_parents(tmp_path, ["p1"])
    assert got["p1"].section_id is None and got["p1"].section_heading == "H"


def test_extended_stops_at_section_id_boundary_even_with_equal_headings(tmp_path):
    upsert_parents(tmp_path, "x.pdf", [
        _p("p1", "x.pdf", "a" * 10, "Actions", sid="s_k"),
        _p("p2", "x.pdf", "b" * 10, "Actions", sid="s_m"),
    ])
    got = fetch_parents_extended(tmp_path, ["p1"])
    assert got["p1"].text == "a" * 10


# ---------------------------------------------------------------------------
# unit_fts — persisted FTS5 lexical index (roadmap 1.6, S5)
# ---------------------------------------------------------------------------


def test_fts_rows_follow_units_per_source(tmp_path):
    upsert_units_fts(tmp_path, "a.pdf", [("a_0", 0, "a.pdf", "OSR", "p1", "Combat\n\nthe owlbear has THAC0 15"),
                                         ("a_1", 1, "a.pdf", "OSR", "p1", "rounds have phases")])
    upsert_units_fts(tmp_path, "b.pdf", [("b_0", 0, "b.pdf", "5E", "p2", "fireball deals 8d6")])
    assert count_units_fts(tmp_path) == 3
    upsert_units_fts(tmp_path, "a.pdf", [("a_9", 0, "a.pdf", "OSR", "p1", "replaced")])
    assert count_units_fts(tmp_path, "a.pdf") == 1
    assert delete_units_fts_for_source(tmp_path, "b.pdf") == 1
    assert count_units_fts(tmp_path) == 1


def test_fts_search_is_scoped_by_where(tmp_path):
    upsert_units_fts(tmp_path, "/lib/a.pdf", [("a_0", 0, "a.pdf", "OSR", "p1", "owlbear THAC0 15")])
    upsert_units_fts(tmp_path, "/lib/b.pdf", [("b_0", 0, "b.pdf", "5E", "p2", "owlbear AC 13")])
    assert set(search_units_fts(tmp_path, '"owlbear"', 10, None)) == {"a_0", "b_0"}
    assert search_units_fts(tmp_path, '"owlbear"', 10, {"filename": "b.pdf"}) == ["b_0"]
    assert search_units_fts(tmp_path, '"owlbear"', 10, {"source": {"$in": ["/lib/a.pdf"]}}) == ["a_0"]
    assert search_units_fts(tmp_path, '"owlbear"', 10, {"$and": [{"game_system": "5E"}, {"filename": "b.pdf"}]}) == ["b_0"]


def test_where_to_sql_rejects_unknown_operators():
    import pytest
    with pytest.raises(ValueError):
        where_to_sql({"filename": {"$ne": "x"}})
    with pytest.raises(ValueError):
        where_to_sql({"page_start": 3})


def test_where_to_sql_degenerate_shapes():
    """An unscoped sub-clause is TRUE; an empty $or matches nothing."""
    assert where_to_sql({"$and": []}) == ("", [])
    assert where_to_sql({"$and": [{}, {"filename": "a.pdf"}]}) == ("(filename = ?)", ["a.pdf"])
    assert where_to_sql({"$or": [{}, {"filename": "a.pdf"}]}) == ("", [])
    assert where_to_sql({"$or": []}) == ("0", [])


def test_fts_search_with_an_empty_or_returns_nothing(tmp_path):
    upsert_units_fts(tmp_path, "/lib/a.pdf", [("a_0", 0, "a.pdf", "OSR", "p1", "owlbear")])
    assert search_units_fts(tmp_path, '"owlbear"', 5, {"$or": []}) == []


def test_rename_source_rewrites_ids_from_ordinals(tmp_path):
    upsert_parents(tmp_path, "/old/a.pdf", [_parent("p1", "/old/a.pdf")])
    upsert_units_fts(tmp_path, "/old/a.pdf", [("h_a_0", 0, "a.pdf", "OSR", "p1", "text"), ("h_a_1", 1, "a.pdf", "OSR", "p1", "more")])
    rename_source(tmp_path, "/old/a.pdf", "/new/b.pdf", "b.pdf", "deadbeef_b")
    assert count_units_fts(tmp_path, "/old/a.pdf") == 0
    assert search_units_fts(tmp_path, '"more"', 5, {"filename": "b.pdf"}) == ["deadbeef_b_1"]
    assert fetch_parents(tmp_path, ["p1"])["p1"].source_pdf == "/new/b.pdf"


def test_update_units_fts_game_system_retags_one_source(tmp_path):
    upsert_units_fts(tmp_path, "/lib/a.pdf", [("a_0", 0, "a.pdf", "OSR", "p1", "owlbear THAC0 15")])
    upsert_units_fts(tmp_path, "/lib/b.pdf", [("b_0", 0, "b.pdf", "OSR", "p2", "owlbear AC 13")])
    assert update_units_fts_game_system(tmp_path, "/lib/a.pdf", "5E") == 1
    assert search_units_fts(tmp_path, '"owlbear"', 5, {"game_system": "5E"}) == ["a_0"]
    assert search_units_fts(tmp_path, '"owlbear"', 5, {"game_system": "OSR"}) == ["b_0"]


# ---------------------------------------------------------------------------
# Section assembly by section_path prefix (roadmap 2.1)
# ---------------------------------------------------------------------------

# A monster chapter: Monsters (s_m) > Kraken (s_k) > {Actions (s_ka), Legendary (s_kl)}; Medusa (s_d) > Actions (s_da)
def _monster_tree(tmp_path):
    rows = [
        _p("p_intro", "x.pdf", "Monsters intro " * 20, "Monsters", 1, 1, sid="s_m", path="s_m"),
        _p("p_kra", "x.pdf", "Kraken AC 18 HP 472 " * 30, "Monsters > Kraken", 2, 2, sid="s_k", path="s_m/s_k"),
        _p("p_kra_act", "x.pdf", "Tentacle attack " * 30, "Monsters > Kraken > Actions", 2, 3, sid="s_ka", path="s_m/s_k/s_ka"),
        _p("p_kra_leg", "x.pdf", "Ink cloud legendary " * 30, "Monsters > Kraken > Legendary Actions", 3, 3, sid="s_kl", path="s_m/s_k/s_kl"),
        _p("p_med", "x.pdf", "Medusa AC 15 " * 30, "Monsters > Medusa", 4, 4, sid="s_d", path="s_m/s_d"),
        _p("p_med_act", "x.pdf", "Petrifying gaze " * 30, "Monsters > Medusa > Actions", 4, 4, sid="s_da", path="s_m/s_d/s_da"),
    ]
    upsert_parents(tmp_path, "x.pdf", rows)
    return rows


def test_prefix_range_covers_self_and_descendants_only():
    lo, hi = _prefix_range("s_m/s_k")
    assert lo == "s_m/s_k" and hi == "s_m/s_k0"
    assert lo <= "s_m/s_k" < hi and lo <= "s_m/s_k/s_ka" < hi
    assert not (lo <= "s_m/s_d" < hi) and not (lo <= "s_m/s_kz" < hi)   # 'z' > '0'


def test_section_root_is_the_shallowest_ancestor_that_fits(tmp_path):
    _monster_tree(tmp_path)
    with _txn(tmp_path) as conn:
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


def test_assemble_section_returns_the_subtree_in_document_order(tmp_path):
    _monster_tree(tmp_path)
    with _txn(tmp_path) as conn:
        doc = assemble_section(conn, "x.pdf", "s_m/s_k", "p_kra_act", cap=2000)
    assert doc.text.startswith("Kraken AC 18") and "Ink cloud" in doc.text
    assert doc.text.index("Tentacle") < doc.text.index("Ink cloud")
    assert (doc.page_start, doc.page_end) == (2, 3)
    assert doc.section_heading == "Monsters > Kraken"
    assert doc.section_id == "s_k" and doc.windowed is False


def test_assemble_section_heading_truncates_to_root_depth(tmp_path):
    """The root is shallower than the first row's own breadcrumb: the
    heading must be cut to the root's depth, not the row's full chain."""
    upsert_parents(tmp_path, "z.pdf", [
        _p("p_leaf", "z.pdf", "Leaf text", "Chapter > Sub > Leaf", 1, 1, sid="s_l", path="s_c/s_s/s_l"),
    ])
    with _txn(tmp_path) as conn:
        doc = assemble_section(conn, "z.pdf", "s_c/s_s", "p_leaf", cap=SECTION_CAP)
    assert doc.section_heading == "Chapter > Sub"


def test_assemble_section_windows_a_leaf_larger_than_the_cap(tmp_path):
    rows = [_p(f"p{i}", "y.pdf", f"para{i} " * 40, "Long > Section", 1, 1, sid="s_l", path="s_x/s_l") for i in range(10)]
    upsert_parents(tmp_path, "y.pdf", rows)
    with _txn(tmp_path) as conn:
        doc = assemble_section(conn, "y.pdf", "s_x/s_l", "p5", cap=900)
    assert doc.windowed is True
    assert "para5" in doc.text and len(doc.text) <= 900
    assert "para4" in doc.text or "para6" in doc.text          # grows outward from the match
    assert "para0" not in doc.text and "para9" not in doc.text


def test_fetch_sections_falls_back_to_the_heading_walk_for_legacy_rows(tmp_path):
    upsert_parents(tmp_path, "old.pdf", [_p("a", "old.pdf", "one", "H"), _p("b", "old.pdf", "two", "H")])
    got = fetch_sections(tmp_path, [("a", None, "old.pdf")])
    assert got["a"].text == "one\n\ntwo" and got["a"].root_path == ""


def test_fetch_sections_batches_and_keys_by_parent_id(tmp_path):
    _monster_tree(tmp_path)
    got = fetch_sections(tmp_path, [("p_kra_act", "s_m/s_k/s_ka", "x.pdf"), ("p_med", "s_m/s_d", "x.pdf")])
    assert set(got) == {"p_kra_act", "p_med"}
    assert got["p_kra_act"].root_path == got["p_med"].root_path == "s_m"   # both fit under the chapter at 6 000


def _count_aggregates(conn) -> list[str]:
    """Collect the subtree-size aggregates SQLite actually runs."""
    sql: list[str] = []
    conn.set_trace_callback(
        lambda s: sql.append(s) if "SUM(LENGTH(text))" in s else None)
    return sql


def test_section_root_for_memoises_the_subtree_aggregates(tmp_path):
    """The depth-1 aggregate re-sums the whole chapter's text; candidates
    from one chapter must pay for it once per request, not once each."""
    _monster_tree(tmp_path)
    with _txn(tmp_path) as conn:
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


def test_section_root_for_is_none_when_the_source_has_no_parents(tmp_path):
    """An empty subtree measures 0 chars and would otherwise "fit" at
    depth 1, collapsing every hit in the book onto one root."""
    _monster_tree(tmp_path)
    with _txn(tmp_path) as conn:
        assert section_root_for(conn, "gone.pdf", "s_m/s_k/s_ka") is None
        assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka") == "s_m"


def test_fetch_sections_omits_a_hit_whose_source_has_no_parents(tmp_path):
    _monster_tree(tmp_path)
    assert fetch_sections(tmp_path, [("ghost", "s_m/s_k", "gone.pdf")]) == {}


def test_fetch_sections_uses_a_root_the_caller_already_computed(tmp_path):
    """The search path picks each hit's root while deduping and hands it
    over; the assembly must take it rather than recompute (which would
    return the whole chapter here)."""
    _monster_tree(tmp_path)
    got = fetch_sections(tmp_path, [("p_kra_act", "s_m/s_k/s_ka", "x.pdf")],
                         roots={"p_kra_act": "s_m/s_k"})
    assert got["p_kra_act"].root_path == "s_m/s_k"
    assert "Medusa" not in got["p_kra_act"].text


# ---------------------------------------------------------------------------
# fetch_section_by_id — resolve an advertised id, row of its own or not
# ---------------------------------------------------------------------------

def test_fetch_section_by_id_assembles_a_section_that_owns_a_row(tmp_path):
    _monster_tree(tmp_path)
    doc = fetch_section_by_id(tmp_path, "s_k")
    assert doc is not None
    assert doc.section_id == "s_k" and doc.root_path == "s_m/s_k"
    assert "Ink cloud" in doc.text and "Medusa" not in doc.text


def test_fetch_section_by_id_resolves_a_container_with_no_row_of_its_own(tmp_path):
    """A heading immediately followed by a sub-heading owns no chunk, so
    no parents row carries its section_id — yet `section_root_for` picks
    it as the section root and search advertises that id. Resolution has
    to go through the path segments, not the section_id column."""
    upsert_parents(tmp_path, "x.pdf", [
        _p("p_kra", "x.pdf", "Kraken AC 18 " * 5, "Monsters > Kraken",
           2, 2, sid="s_k", path="s_m/s_k"),
        _p("p_med", "x.pdf", "Medusa AC 15 " * 5, "Monsters > Medusa",
           4, 4, sid="s_d", path="s_m/s_d"),
    ])
    doc = fetch_section_by_id(tmp_path, "s_m")
    assert doc is not None
    assert doc.section_id == "s_m" and doc.root_path == "s_m"
    assert "Kraken" in doc.text and "Medusa" in doc.text
    assert doc.section_heading == "Monsters"
    assert (doc.page_start, doc.page_end) == (2, 4)


def test_fetch_section_by_id_resolves_a_middle_segment(tmp_path):
    """The id can sit anywhere in the path: here `s_k` is a middle
    segment whose own row was never written."""
    upsert_parents(tmp_path, "x.pdf", [
        _p("p_act", "x.pdf", "Tentacle attack " * 5,
           "Monsters > Kraken > Actions", 2, 3, sid="s_ka",
           path="s_m/s_k/s_ka"),
        _p("p_leg", "x.pdf", "Ink cloud " * 5,
           "Monsters > Kraken > Legendary Actions", 3, 3, sid="s_kl",
           path="s_m/s_k/s_kl"),
    ])
    doc = fetch_section_by_id(tmp_path, "s_k")
    assert doc is not None
    assert doc.root_path == "s_m/s_k" and doc.section_id == "s_k"
    assert "Tentacle" in doc.text and "Ink cloud" in doc.text


def test_fetch_section_by_id_unknown_id_is_none(tmp_path):
    _monster_tree(tmp_path)
    assert fetch_section_by_id(tmp_path, "s_nowhere") is None


def test_count_phrases_counts_units_with_the_adjacent_pair(tmp_path):
    from parents_store import count_phrases

    upsert_units_fts(tmp_path, "/lib/a.pdf", [
        ("a_0", 0, "a.pdf", "OSR", "p1", "Thief skills table"),
        ("a_1", 1, "a.pdf", "OSR", "p1", "the thief skill of climbing"),
        ("a_2", 2, "a.pdf", "OSR", "p1", "skill of this thief"),
    ])
    got = count_phrases(tmp_path, [("thief", "skill"), ("this", "skill"), ('bad"', "skill")])
    assert got[("thief", "skill")] == 2      # porter stems "skills" → "skill"
    assert got[("this", "skill")] == 0       # not adjacent in that order
    assert got[('bad"', "skill")] == 0       # quotes stripped, no FTS syntax error
    assert count_phrases(tmp_path, []) == {}

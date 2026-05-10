"""Unit tests for parents_store — SQLite-backed parent KV store."""

from granularity import ParentDoc
from parents_store import (
    upsert_parents,
    fetch_parents,
    fetch_parents_extended,
    delete_parents_for_source,
    clear_all_parents,
    count_parents,
)


def _p(
    pid: str,
    source_pdf: str,
    text: str,
    section: str | None,
    page_start: int = 1,
    page_end: int = 1,
    chunk_type: str = "prose",
) -> ParentDoc:
    return ParentDoc(
        parent_id=pid,
        text=text,
        section_heading=section,
        chunk_type=chunk_type,
        source_pdf=source_pdf,
        page_start=page_start,
        page_end=page_end,
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

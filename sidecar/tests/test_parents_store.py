"""Unit tests for parents_store — SQLite-backed parent KV store."""

from granularity import ParentDoc
from parents_store import (
    upsert_parents,
    fetch_parents,
    delete_parents_for_source,
    clear_all_parents,
    count_parents,
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

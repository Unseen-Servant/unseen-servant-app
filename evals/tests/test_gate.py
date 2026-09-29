"""Per-page min gate for the golden extraction set (recovery strategy W0.2).

The 30-page mean let g28 drop 1.0 → 0.5 inside a 0.94 aggregate that "beat
v2" — three times over. The gate compares every page's every metric against a
reference baseline; any drop fails the run, whatever the mean does.
"""
from evals.extraction import gate


def test_page_below_reference_is_a_regression():
    ref = [{"id": "g28", "kind": "table", "content_recall": 1.0, "table_cells": 1.0}]
    cur = [{"id": "g28", "kind": "table", "content_recall": 1.0, "table_cells": 0.5}]
    assert gate.page_regressions(cur, ref) == [
        {"id": "g28", "metric": "table_cells", "ref": 1.0, "cur": 0.5}]


def test_rising_mean_does_not_hide_a_falling_page():
    ref = [{"id": "g01", "table_cells": 0.8}, {"id": "g02", "table_cells": 0.8}, {"id": "g03", "table_cells": 1.0}]
    cur = [{"id": "g01", "table_cells": 1.0}, {"id": "g02", "table_cells": 1.0}, {"id": "g03", "table_cells": 0.9}]
    assert [r["id"] for r in gate.page_regressions(cur, ref)] == ["g03"]


def test_new_pages_and_unscored_metrics_are_not_regressions():
    ref = [{"id": "g01", "reading_order": 1.0}]
    cur = [{"id": "g01", "reading_order": None}, {"id": "g99", "reading_order": 0.0}]
    assert gate.page_regressions(cur, ref) == []


def test_equal_within_tolerance_passes():
    ref = [{"id": "g01", "content_recall": 2 / 3}]
    cur = [{"id": "g01", "content_recall": 0.6666666666}]
    assert gate.page_regressions(cur, ref) == []


def test_format_lists_each_regression_on_one_line():
    out = gate.format_regressions([{"id": "g28", "metric": "table_cells", "ref": 1.0, "cur": 0.5}])
    assert "g28" in out and "table_cells" in out and "1.000" in out and "0.500" in out
    assert gate.format_regressions([]) == "no per-page regressions"

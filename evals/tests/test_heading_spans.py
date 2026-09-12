from types import SimpleNamespace

from evals.retrieval.heading_spans import leaf_spans


def test_leaf_spans_count_pages_and_children():
    pages = [SimpleNamespace(page_number=1, markdown="# A\n\n## B\n\ntext"),
             SimpleNamespace(page_number=2, markdown="text"),
             SimpleNamespace(page_number=3, markdown="# C\n\ntext")]
    out = leaf_spans(pages)
    assert ("B", 3, False) in out      # pages 1–3, no child
    assert ("A", 3, True) in out       # had B
    assert ("C", 1, False) in out

"""Runner guards that keep invalid retrieval runs out of baselines."""
from types import SimpleNamespace

import pytest

from evals.engines.base import IndexReport
from evals.run_eval import (
    corpus_fingerprint,
    format_retrieval_regressions,
    retrieval_regressions,
    run,
)


def _result(all_mrr: float, single_mrr: float) -> dict:
    return {
        "by_scope": {
            "all": {"mrr@5": all_mrr, "recall@3": 0.8},
            "single": {"mrr@5": single_mrr, "recall@3": 0.7},
        }
    }


def test_retrieval_gate_checks_all_shared_scopes():
    current = _result(0.8, 0.6)
    reference = _result(0.7, 0.7)
    assert retrieval_regressions(current, reference) == [
        {"scope": "single", "metric": "mrr@5", "ref": 0.7, "cur": 0.6}
    ]


def test_retrieval_gate_report_names_regression():
    out = format_retrieval_regressions([
        {"scope": "all", "metric": "recall@3", "ref": 0.8, "cur": 0.7}
    ])
    assert "all" in out and "recall@3" in out and "0.800" in out and "0.700" in out


def test_corpus_fingerprint_binds_document_ids_and_digests():
    a = SimpleNamespace(documents=[
        SimpleNamespace(id="a", pdf_sha256="pdf-a", ref_digest="refs-a"),
        SimpleNamespace(id="b", pdf_sha256="pdf-b", ref_digest="refs-b"),
    ])
    b = SimpleNamespace(documents=[
        SimpleNamespace(id="b", pdf_sha256="pdf-b", ref_digest="refs-b"),
        SimpleNamespace(id="a", pdf_sha256="pdf-a", ref_digest="refs-a"),
    ])
    changed = SimpleNamespace(documents=[
        SimpleNamespace(id="a", pdf_sha256="pdf-a", ref_digest="refs-changed"),
        SimpleNamespace(id="b", pdf_sha256="pdf-b", ref_digest="refs-b"),
    ])
    assert corpus_fingerprint(a) == corpus_fingerprint(b)
    assert corpus_fingerprint(a) != corpus_fingerprint(changed)


def test_index_error_aborts_before_warmup(tmp_path):
    class BrokenEngine:
        def index(self, _paths):
            return IndexReport(requested=1, indexed=0, skipped=0, errors=["bad PDF"])

        def warmup(self, _opts):
            raise AssertionError("warmup must not run after an index failure")

    corpus = SimpleNamespace(documents=[
        SimpleNamespace(id="book", pdf_path=tmp_path / "book.pdf")
    ])
    query = {"id": "q1", "doc": "book"}
    with pytest.raises(SystemExit, match="indexing failed"):
        run(BrokenEngine(), [query], corpus, SimpleNamespace(), do_index=True)

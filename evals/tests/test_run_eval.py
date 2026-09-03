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


from evals.engines.base import SearchOptions, SearchResponse


class _TagRecorder:
    """Engine double: indexes nothing, records tag calls, answers empty."""

    def __init__(self):
        self.tagged: list[tuple[str, str, list[str]]] = []

    def index(self, _paths):
        return IndexReport(requested=1, indexed=0, skipped=1)

    def tag_systems(self, filename, tag, keywords):
        self.tagged.append((filename, tag, list(keywords)))

    def warmup(self, _opts):
        pass

    def search(self, _query, _opts):
        return SearchResponse(results=[], latency_ms=1.0)


def _corpus(tmp_path, *ids):
    return SimpleNamespace(documents=[
        SimpleNamespace(id=i, pdf_path=tmp_path / f"{i}.pdf") for i in ids
    ])


def _query(qid, doc, scope="cued"):
    return {"id": qid, "pair": qid, "style": "keyword", "category": "prose_rule",
            "scope": scope, "doc": doc, "query": "x", "anchors": ["x"]}


def test_run_tags_every_needed_doc_after_indexing(tmp_path):
    engine = _TagRecorder()
    corpus = _corpus(tmp_path, "osric_2e", "yze_srd")
    tags = {"osric_2e": ("OSRIC", ["osric"]), "yze_srd": ("Year Zero Engine", ["year zero", "yze"])}
    run(engine, [_query("q1", "osric_2e"), _query("q2", "yze_srd")], corpus,
        SearchOptions(), do_index=True, tags=tags)
    assert sorted(engine.tagged) == [
        ("osric_2e.pdf", "OSRIC", ["osric"]),
        ("yze_srd.pdf", "Year Zero Engine", ["year zero", "yze"]),
    ]


def test_run_never_tags_a_reused_index(tmp_path):
    engine = _TagRecorder()
    run(engine, [_query("q1", "osric_2e")], _corpus(tmp_path, "osric_2e"),
        SearchOptions(), do_index=False, tags={"osric_2e": ("OSRIC", ["osric"])})
    assert engine.tagged == []


def test_run_skips_tagging_when_engine_lacks_the_hook(tmp_path):
    class NoTag:
        def index(self, _paths):
            return IndexReport(requested=1, indexed=0, skipped=1)

        def warmup(self, _opts):
            pass

        def search(self, _query, _opts):
            return SearchResponse(results=[], latency_ms=1.0)

    result = run(NoTag(), [_query("q1", "osric_2e")], _corpus(tmp_path, "osric_2e"),
                 SearchOptions(), do_index=True, tags={"osric_2e": ("OSRIC", ["osric"])})
    assert result["per_query"][0]["hit_rank"] is None


from evals.engines.base import SearchResult
from evals.run_eval import query_docs


class _TwinEngine:
    """Returns the 5.2.1 twin at rank 1 and 5.1 at rank 2 for every query."""

    def index(self, _paths):
        return IndexReport(requested=1, indexed=0, skipped=1)

    def warmup(self, _opts):
        pass

    def search(self, _query, _opts):
        def hit(fn):
            return SearchResult(text="magic missile 1d4 1", filename=fn, source=fn,
                                section_heading="", page_start=1, page_end=1,
                                relevance=1.0, tier="strong", reranked=False)
        return SearchResponse(results=[hit("srd_5_2_1.pdf"), hit("srd_5_1.pdf")], latency_ms=1.0)


def test_query_docs_normalises_str_list_and_any():
    assert query_docs({"doc": "srd_5_1"}) == ["srd_5_1"]
    assert query_docs({"doc": ["srd_5_1", "srd_5_2_1"]}) == ["srd_5_1", "srd_5_2_1"]
    assert query_docs({"doc": "any"}) == []


def test_cued_query_with_doc_list_accepts_the_twin(tmp_path):
    corpus = _corpus(tmp_path, "srd_5_1", "srd_5_2_1")
    q = _query("q043", ["srd_5_1", "srd_5_2_1"])
    q["anchors"] = ["magic missile", "1d4 1"]
    result = run(_TwinEngine(), [q], corpus, SearchOptions(), do_index=False)
    assert result["per_query"][0]["hit_rank"] == 1


def test_single_scope_rejects_a_doc_list(tmp_path):
    corpus = _corpus(tmp_path, "srd_5_1", "srd_5_2_1")
    q = _query("q001", ["srd_5_1", "srd_5_2_1"], scope="single")
    with pytest.raises(SystemExit, match="single-scope"):
        run(_TwinEngine(), [q], corpus, SearchOptions(), do_index=False)


def test_v2_request_body_is_json_serialisable_with_default_extra():
    """The v2 adapter posts opts.extra as JSON; the runner must not hand it
    v3's system_map (a dict of sets) — v2 gets tags instead."""
    import json

    from evals.engines.v2 import V2Engine

    body = V2Engine(data_dir="/nonexistent")._request_body("q", SearchOptions())
    json.dumps(body)
    assert "system_map" not in body

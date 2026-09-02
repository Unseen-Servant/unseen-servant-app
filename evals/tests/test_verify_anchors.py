"""verify_anchors: every anchor in ref ∧ PDF of the primary doc, and in the
PDF of every secondary (edition-twin) doc."""
from evals.retrieval.verify_anchors import verify_query


class _Text:
    def __init__(self, ref: str, pdf: str):
        self._ref, self._pdf = ref, pdf

    def ref_norm(self, _answer_ref):
        return self._ref

    def pdf_norm(self):
        return self._pdf

    def anchor_pages(self, _anchor):
        return [1]


def test_primary_needs_ref_and_pdf_secondary_needs_pdf_only():
    by_id = {
        "srd_5_1": _Text(ref="magic missile 1d4 1", pdf="magic missile 1d4 1"),
        "srd_5_2_1": _Text(ref="", pdf="magic missile 1d4 1"),
    }
    q = {"id": "q043", "category": "exact_name", "doc": ["srd_5_1", "srd_5_2_1"],
         "anchors": ["magic missile", "1d4 1"]}
    assert verify_query(q, by_id) == []


def test_secondary_missing_the_anchor_fails():
    by_id = {
        "srd_5_1": _Text(ref="magic missile", pdf="magic missile"),
        "srd_5_2_1": _Text(ref="", pdf="fireball"),
    }
    q = {"id": "q043", "category": "exact_name", "doc": ["srd_5_1", "srd_5_2_1"],
         "anchors": ["magic missile"]}
    fails = verify_query(q, by_id)
    assert fails and "srd_5_2_1" in fails[0]

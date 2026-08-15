"""Authoring guard for queries.yaml — enforces §3's anchor discipline.

The old ground truth was once 30% wrong, so no anchor is trusted: each one
must be found (after the grader's normalization) in BOTH

  1. the digital-native reference file (``answer_ref``, or the doc's ref
     glob) — the clean oracle, and
  2. the PDF the pipeline actually indexes — so the anchor is reachable.

For ``cross_page`` queries it additionally confirms the anchors really do
straddle a physical page break (else the category is a lie).

Run from the repo root under the sidecar env (needs fitz + pyyaml)::

    uv run --project sidecar python -m evals.retrieval.verify_anchors

Exit non-zero if any anchor fails, so this can gate a commit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from evals.corpus import load_corpus
from evals.extraction.ref_loader import ref_text  # shared md/html/odt loader

QUERIES_PATH = Path(__file__).resolve().parent / "queries.yaml"


def norm(text: str) -> str:
    """Grader normalization, verbatim from sidecar/evals/scorer.py."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def anchor_alts(anchor) -> list[str]:
    """An anchor is a string (one form) or a list of any-of alternatives."""
    return anchor if isinstance(anchor, list) else [anchor]


def _hit(text_norm: str, anchor) -> bool:
    return any(norm(alt) in text_norm for alt in anchor_alts(anchor))


class DocText:
    """Lazily-loaded, cached normalized text for one document."""

    def __init__(self, doc):
        self.doc = doc
        self._ref: dict[str, str] = {}
        self._pdf_norm: str | None = None
        self._pages_norm: list[str] | None = None

    def ref_norm(self, answer_ref: str | None) -> str:
        key = answer_ref or "*glob*"
        if key not in self._ref:
            if answer_ref:
                paths = [self.doc.root / answer_ref]
            else:
                paths = self.doc.ref_paths()
            self._ref[key] = norm("\n".join(ref_text(p) for p in paths))
        return self._ref[key]

    def _load_pdf(self):
        import fitz

        with fitz.open(self.doc.pdf_path) as pdf:
            self._pages_norm = [norm(p.get_text()) for p in pdf]
        self._pdf_norm = "\n".join(self._pages_norm)

    def pdf_norm(self) -> str:
        if self._pdf_norm is None:
            self._load_pdf()
        return self._pdf_norm

    def anchor_pages(self, anchor) -> list[int]:
        if self._pages_norm is None:
            self._load_pdf()
        return [
            i + 1
            for i, pg in enumerate(self._pages_norm)
            if any(norm(alt) in pg for alt in anchor_alts(anchor))
        ]


def main() -> int:
    corpus = load_corpus()
    by_id = {d.id: DocText(d) for d in corpus.documents}
    queries = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))

    total_fail = 0
    for q in queries:
        doc_id = q["doc"]
        dt = by_id.get(doc_id)
        if dt is None:
            print(f"✗ {q['id']}: unknown doc {doc_id!r}")
            total_fail += 1
            continue
        ref_n = dt.ref_norm(q.get("answer_ref"))
        pdf_n = dt.pdf_norm()

        fails = []
        for a in q["anchors"]:
            in_ref, in_pdf = _hit(ref_n, a), _hit(pdf_n, a)
            if not (in_ref and in_pdf):
                where = "ref" if not in_ref else ""
                where += ("+" if where and not in_pdf else "") + ("pdf" if not in_pdf else "")
                fails.append(f"{a!r} (missing in {where})")

        cross_note = ""
        if q["category"] == "cross_page":
            page_sets = [set(dt.anchor_pages(a)) for a in q["anchors"]]
            spanned = set().union(*page_sets) if page_sets else set()
            straddles = len(spanned) >= 2 and any(
                page_sets[i] and page_sets[j] and page_sets[i].isdisjoint(page_sets[j])
                for i in range(len(page_sets))
                for j in range(i + 1, len(page_sets))
            )
            cross_note = f"  pages={sorted(spanned)} straddle={'yes' if straddles else 'NO'}"
            if not straddles:
                fails.append("cross_page anchors do NOT straddle a page break")

        if fails:
            total_fail += 1
            print(f"✗ {q['id']:5} [{q['category']:17}] {doc_id}")
            for f in fails:
                print(f"      {f}")
        else:
            print(f"✓ {q['id']:5} [{q['category']:17}] {doc_id}{cross_note}")

    n = len(queries)
    print(f"\n{n - total_fail}/{n} queries fully verified (ref ∧ pdf).")
    if total_fail:
        print(f"✗ {total_fail} queries have unverified anchors — fix before committing.")
        return 1
    print("✓ all anchors verified in both reference and PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

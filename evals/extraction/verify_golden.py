"""Authoring guard for the golden page specs — the extraction-axis twin of
retrieval/verify_anchors.py.

Every expected phrase (content / order / cells) must be REAL: its tokens
present in BOTH the digital-native reference and the raw PDF page
(``fitz.get_text`` — not the engine's pipeline). Verification is
token-level, not contiguous, so a table cell like "climb walls 80" passes
even though the raw PDF lays the header and value out in separate columns —
the *contiguity* of that cell is what grade.py measures on the engine's
extraction, not what makes the spec valid.

    uv run --project sidecar python -m evals.extraction.verify_golden

Exit non-zero if any phrase is unverified.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from evals.corpus import require_corpus
from evals.extraction.ref_loader import ref_text
from evals.retrieval.grade import normalize

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def load_golden() -> list[dict]:
    specs: list[dict] = []
    for path in sorted(GOLDEN_DIR.glob("*.yaml")):
        specs.extend(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    return specs


def _tokens_present(text_wrapped: str, phrase) -> bool:
    """True if some alternative's tokens are all present (anywhere) as
    whole tokens in the wrapped normalized text."""
    alts = phrase if isinstance(phrase, list) else [phrase]
    for alt in alts:
        toks = normalize(alt).split()
        if toks and all(f" {t} " in text_wrapped for t in toks):
            return True
    return False


def _pdf_page_text(pdf_path: Path, page: int) -> str:
    import fitz

    with fitz.open(pdf_path) as doc:
        return doc.load_page(page - 1).get_text()


def main() -> int:
    corpus = require_corpus()
    by_id = {d.id: d for d in corpus.documents}
    specs = load_golden()
    if not specs:
        print("no golden specs found in evals/extraction/golden/")
        return 1

    total_fail = 0
    for spec in specs:
        doc = by_id.get(spec["doc"])
        if doc is None:
            print(f"✗ {spec['id']}: unknown doc {spec['doc']!r}")
            total_fail += 1
            continue
        ref_path = doc.root / spec["answer_ref"]
        ref_w = f" {normalize(ref_text(ref_path))} "
        pdf_w = f" {normalize(_pdf_page_text(doc.pdf_path, spec['page']))} "

        phrases = list(spec.get("content", [])) + list(spec.get("order", [])) + list(spec.get("cells", []))
        fails = []
        for p in phrases:
            in_ref, in_pdf = _tokens_present(ref_w, p), _tokens_present(pdf_w, p)
            if not (in_ref and in_pdf):
                where = "ref" if not in_ref else ""
                where += ("+" if where and not in_pdf else "") + (f"pdf p.{spec['page']}" if not in_pdf else "")
                fails.append(f"{p!r} (missing in {where})")

        if fails:
            total_fail += 1
            print(f"✗ {spec['id']:5} [{spec['kind']:10}] {spec['doc']} p.{spec['page']}")
            for f in fails:
                print(f"      {f}")
        else:
            print(f"✓ {spec['id']:5} [{spec['kind']:10}] {spec['doc']} p.{spec['page']} "
                  f"({len(phrases)} phrases)")

    n = len(specs)
    print(f"\n{n - total_fail}/{n} golden pages fully verified (ref ∧ pdf).")
    if total_fail:
        print(f"✗ {total_fail} have unverified phrases — fix before committing.")
        return 1
    print("✓ all golden phrases verified in both reference and PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

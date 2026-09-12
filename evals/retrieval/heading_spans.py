"""How many pages does each heading stay on the chunker's stack, and did it
get a child? Measured 2026-09-11 on the Phase 1 tree: p99 = 2 pages, but the
tail is legitimate leaf sections, so no cap was built (see the Phase 1 plan
ledger).

    uv run --project sidecar python -m evals.retrieval.heading_spans
"""
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sidecar"))

from evals.corpus import require_corpus  # noqa: E402

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def leaf_spans(pages: list) -> list[tuple[str, int, bool]]:
    """(heading, pages_on_stack, had_child) for every heading pushed."""
    stack: list[list] = []          # [level, text, page_pushed, had_child]
    done: list[tuple[str, int, bool]] = []
    last_page = 0
    for page in pages:
        last_page = page.page_number
        for line in page.markdown.splitlines():
            m = _HEADING_RE.match(line)
            if not m:
                continue
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                lvl, text, since, child = stack.pop()
                done.append((text, page.page_number - since + 1, child))
            if stack:
                stack[-1][3] = True
            stack.append([level, m.group(2), page.page_number, False])
    for lvl, text, since, child in stack:
        done.append((text, last_page - since + 1, child))
    return done


def main() -> int:
    import server  # noqa: F401  (sidecar import path set above)
    from server import _extract_pdf_pages

    corpus = require_corpus()
    rows = []
    for d in corpus.documents:
        pages = _extract_pdf_pages(d.pdf_path)
        for text, span, child in leaf_spans(pages):
            rows.append((d.id, text, span, child))
    leaves = sorted(r[2] for r in rows if not r[3])
    if not leaves:
        print("no childless headings")
        return 0
    q = statistics.quantiles(leaves, n=100)
    print(f"childless headings: {len(leaves)}  p50 {q[49]}  p90 {q[89]}  p99 {q[98]}  max {leaves[-1]}")
    worst = sorted((r for r in rows if not r[3]), key=lambda r: -r[2])[:15]
    for doc, text, span, _ in worst:
        print(f"  {doc:<12}{span:>5} pages  {text[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The eval harness must mimic the application experience.

The 2026-07-10 #340 regression shipped because the harness requested
n_results=10 while the UI sends 25 (PAGE_SIZE_INITIAL): a pipeline whose
rerank pool scaled with n_results passed the gate at a page size the app
never uses. These tests pin the harness's default request size to the
frontend constant so the two cannot drift apart silently.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_SVELTE = REPO_ROOT / "src" / "routes" / "+page.svelte"


def _ui_initial_page_size() -> int:
    match = re.search(
        r"const PAGE_SIZE_INITIAL = (\d+)", PAGE_SVELTE.read_text()
    )
    assert match, f"PAGE_SIZE_INITIAL not found in {PAGE_SVELTE}"
    return int(match.group(1))


def test_eval_default_page_size_matches_ui_first_page():
    from evals.run_eval import DEFAULT_PAGE_SIZE

    assert DEFAULT_PAGE_SIZE == _ui_initial_page_size(), (
        "evals.run_eval.DEFAULT_PAGE_SIZE must track PAGE_SIZE_INITIAL in "
        "src/routes/+page.svelte — the eval gates quality at the page size "
        "the UI actually sends (metrics stay graded @TOP_K)"
    )

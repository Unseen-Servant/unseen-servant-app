"""The harness must request what the app requests.

The 2026-07-10 #340 regression shipped because an eval asked for
n_results=10 while the UI sends 25 (PAGE_SIZE_INITIAL): a pipeline whose
rerank pool scaled with n_results passed the gate at a page size the app
never uses. sidecar/tests/test_eval_config.py pins the legacy harness;
this pins the one every engine's default request goes through.
"""
import re
from pathlib import Path

from evals.engines.base import SearchOptions

PAGE_SVELTE = Path(__file__).resolve().parents[2] / "src" / "routes" / "legend-lore" / "+page.svelte"


def test_default_request_size_is_the_ui_first_page():
    match = re.search(r"const PAGE_SIZE_INITIAL = (\d+)", PAGE_SVELTE.read_text())
    assert match, f"PAGE_SIZE_INITIAL not found in {PAGE_SVELTE}"
    assert SearchOptions().n_results == int(match.group(1)), (
        "evals.engines.base.SearchOptions.n_results must track PAGE_SIZE_INITIAL "
        "in src/routes/legend-lore/+page.svelte — quality is gated at the page "
        "size the UI actually sends (metrics stay graded @10)"
    )

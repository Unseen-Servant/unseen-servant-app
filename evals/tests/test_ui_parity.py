"""The harness must request what the app requests.

The 2026-07-10 #340 regression shipped because an eval asked for
n_results=10 while the UI sends 25 (PAGE_SIZE_INITIAL): a pipeline whose
rerank pool scaled with n_results passed the gate at a page size the app
never uses. sidecar/tests/test_eval_config.py pins the legacy harness;
this pins the one every engine's default request goes through.
"""
import re
import sys
from dataclasses import asdict
from pathlib import Path

from evals.engines.base import SearchOptions
from evals.engines.v2 import SIDECAR_DIR

PANEL_SVELTE = Path(__file__).resolve().parents[2] / "src" / "lib" / "legend-lore" / "LegendLorePanel.svelte"


def test_default_request_size_is_the_ui_first_page():
    match = re.search(r"const PAGE_SIZE_INITIAL = (\d+)", PANEL_SVELTE.read_text())
    assert match, f"PAGE_SIZE_INITIAL not found in {PANEL_SVELTE}"
    assert SearchOptions().n_results == int(match.group(1)), (
        "evals.engines.base.SearchOptions.n_results must track PAGE_SIZE_INITIAL "
        "in src/lib/legend-lore/LegendLorePanel.svelte — quality is gated at the page "
        "size the UI actually sends (metrics stay graded @10)"
    )


def test_default_knobs_are_the_apps_search_defaults():
    """A bare SearchOptions() must measure what the app ships. The harness
    sends every knob explicitly, so a stale default here silently
    measures a configuration nobody runs (hybrid was off here for a week
    after the app turned it on, 2026-09-23)."""
    if str(SIDECAR_DIR) not in sys.path:
        sys.path.append(str(SIDECAR_DIR))  # append: see v2._import_sidecar
    from legend_lore.service import SearchSettings

    app = SearchSettings().model_dump()
    harness = asdict(SearchOptions())
    shared = ["rerank", "hybrid", "spell_correction", "variant_expansion"]
    assert {k: harness[k] for k in shared} == {k: app[k] for k in shared}

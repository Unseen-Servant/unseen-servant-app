"""Blind round: readability tick + readable@5 (recovery strategy W0.4).

The 2026-08-17 v3 blind sheet was unscorable because the chunks were garbage;
anchors could not see it. A per-chunk "garbled" tick turns that into a number.
"""
import json

from evals.blind import generate, score


def _write_stem(tmp_path, labels: dict) -> str:
    stem = tmp_path / "2026-08-22-v3-test"
    baseline = {"per_query": [
        {"id": "q001", "query": "goblin armor class", "scope": "single"},
        {"id": "q002", "query": "falling damage", "scope": "uncued"},
    ]}
    results = {"results": {
        "q001": [{"rank": r, "book": "SRD.pdf", "section_heading": "Goblin", "page_start": 315,
                  "page_end": 315, "matched": r == 1, "snippet": f"chunk {r}"} for r in range(1, 6)],
        "q002": [{"rank": r, "book": "OSRIC.pdf", "section_heading": "Falling", "page_start": 135,
                  "page_end": 135, "matched": r == 2, "snippet": f"chunk {r}"} for r in range(1, 6)],
    }}
    (tmp_path / f"{stem.name}.json").write_text(json.dumps(baseline))
    (tmp_path / f"{stem.name}.results.json").write_text(json.dumps(results))
    (tmp_path / f"{stem.name}.blind.json").write_text(json.dumps(
        {"baseline": stem.name, "top": 5, "labels": labels}))
    return str(stem)


def test_scoresheet_carries_a_garbled_tick_per_chunk():
    # The sheet's store record must carry `garbled` next to `relevant`, and the
    # rendered chunk row must offer the tick (readable is the default).
    assert "garbled:[]" in generate._TEMPLATE.replace(" ", "")
    assert "data-garbled" in generate._TEMPLATE


def test_readable_at_5_is_one_minus_garbled_share_per_query(tmp_path):
    stem = _write_stem(tmp_path, {
        "q001": {"reviewed": True, "relevant": [1], "garbled": [1, 3]},   # 3/5 readable
        "q002": {"reviewed": True, "relevant": [2], "garbled": []},       # 5/5 readable
    })
    r = score.score(stem)
    assert r["readability"]["single"]["readable@5"] == 0.6
    assert r["readability"]["uncued"]["readable@5"] == 1.0
    assert r["readability"]["all"]["readable@5"] == 0.8
    assert r["readability"]["all"]["garbled"] == 2
    assert [(g["qid"], g["rank"]) for g in r["garbled_chunks"]] == [("q001", 1), ("q001", 3)]


def test_old_exports_without_the_tick_are_not_scored_as_readable(tmp_path):
    stem = _write_stem(tmp_path, {
        "q001": {"reviewed": True, "relevant": [1]},
        "q002": {"reviewed": True, "relevant": [2]},
    })
    r = score.score(stem)
    assert r["readability"]["all"]["readable@5"] is None


def test_report_lists_readability_and_garbled_chunks(tmp_path):
    stem = _write_stem(tmp_path, {
        "q001": {"reviewed": True, "relevant": [1], "garbled": [3]},
        "q002": {"reviewed": True, "relevant": [2], "garbled": []},
    })
    md = score.render_md(stem, score.score(stem))
    assert "readable@5" in md and "0.900" in md
    assert "## Garbled chunks (1)" in md and "q001" in md

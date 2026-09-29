"""Corpus-wide extraction QA (recovery strategy W0.1).

The oracle is the PDF itself: PyMuPDF's native text blocks are column-correct
on the pages where the layout stage interleaves columns, so "does each native
block survive contiguously in the engine's page text?" detects exactly the
defect the 30-page golden mean could not see. Pure functions; no model, no
corpus. Run from the repo root:

    uv run --project sidecar pytest evals/tests
"""
import pymupdf

from evals.extraction import corpus_qa

LEFT = ("Normally the GM rolls this die in secret, because the player\n"
        "has no way of knowing whether no noise was heard because\n"
        "of the roll or because there was no noise to hear. A character\n"
        "who fails to hear noise may try again.")
RIGHT = ("check and success by either indicates the door opens. If the\n"
         "first attempt fails, additional tries may be made at no penalty\n"
         "except for time and noise. Attempting to force a stuck door,\n"
         "and particularly multiple attempts on the same door, is noisy.")
FOOTER = "OSRIC Chapter II — page 156"


def stack(*texts, x0=50.0, y0=100.0, gap=4.0):
    """NativeBlocks stacked down one column, each 12pt per line."""
    out, y = [], y0
    for t in texts:
        h = 12.0 * max(1, len(t.splitlines()))
        out.append(corpus_qa.NativeBlock(t, x0, y, x0 + 240, y + h))
        y += h + gap
    return out


def _interleave(a: str, b: str) -> str:
    return "\n".join(f"{x} {y}" for x, y in zip(a.splitlines(), b.splitlines()))


def test_block_present_contiguously_is_intact():
    r = corpus_qa.grade_page(f"{LEFT}\n\n{RIGHT}", stack(LEFT, RIGHT))
    assert (r["intact"], r["broken"], r["missing"]) == (2, 0, 0)


def test_interleaved_columns_count_as_broken():
    # The shipped v3 layout on OSRIC p156: both columns present, rows merged.
    r = corpus_qa.grade_page(_interleave(LEFT, RIGHT), stack(LEFT, RIGHT))
    assert (r["intact"], r["broken"], r["missing"]) == (0, 2, 0)


def test_dropped_block_is_missing_not_broken():
    # Furniture dropped on purpose must not read as an interleave.
    r = corpus_qa.grade_page(f"{LEFT}\n\n{RIGHT}", stack(LEFT, RIGHT, FOOTER * 8))
    assert (r["intact"], r["broken"], r["missing"]) == (2, 0, 1)


def test_short_blocks_are_not_graded_as_blocks():
    # Table cells / one-line stat fields are short native blocks; row-major
    # table output legitimately reorders them, so they are out of scope here
    # (label_lines covers the stat-block case).
    r = corpus_qa.grade_page("anything", stack("AC 15", "HP 7"))
    assert r["blocks"] == 0


def test_dehyphenation_does_not_break_contiguity():
    # pymupdf4llm (v2) rejoins "tak-\ning" as "taking"; that is not a break.
    native = LEFT.replace("A character", "A char-\nacter")
    r = corpus_qa.grade_page(LEFT, stack(native))
    assert r["intact"] == 1


def test_label_line_torn_from_its_value_is_not_intact():
    native = ["Armor Class 15 (leather armor, shield)", "Hit Points 7 (2d6)"]
    torn = "Armor Class Senses darkvision 60 ft.\n15 (leather armor, shield)\nHit Points 7 (2d6)"
    r = corpus_qa.grade_page(torn, stack(*native), labels=("armor class", "hit points"))
    assert (r["label_lines"], r["label_intact"]) == (2, 1)


def test_native_blocks_come_from_pymupdf_text_blocks(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(pymupdf.Rect(50, 80, 290, 300), LEFT, fontsize=10)
    page.insert_textbox(pymupdf.Rect(320, 80, 560, 300), RIGHT, fontsize=10)
    path = tmp_path / "two_col.pdf"
    doc.save(path)
    blocks = corpus_qa.native_blocks(pymupdf.open(path)[0])
    assert len(blocks) == 2
    assert blocks[0].text.startswith("Normally the GM") and blocks[1].text.startswith("check and success")
    assert blocks[0].x0 < 300 < blocks[1].x0  # bboxes come along, so columns are knowable


def test_aggregate_by_doc_reports_integrity_over_present_blocks():
    pages = [
        {"doc": "a", "page": 1, "blocks": 4, "intact": 3, "broken": 1, "missing": 0,
         "label_lines": 2, "label_intact": 2, "adjacent_pairs": 5, "adjacent_ok": 4},
        {"doc": "a", "page": 2, "blocks": 2, "intact": 0, "broken": 0, "missing": 2,
         "label_lines": 0, "label_intact": 0, "adjacent_pairs": 3, "adjacent_ok": 2},
    ]
    agg = corpus_qa.aggregate(pages)["a"]
    assert agg["adjacency"] == 6 / 8                 # stacked neighbours still consecutive
    assert agg["pages"] == 2
    assert agg["block_integrity"] == 0.75       # intact / (intact + broken)
    assert agg["block_recall"] == 4 / 6         # present (intact + broken) / blocks
    assert agg["label_integrity"] == 1.0
    assert agg["pages_with_broken"] == 1


def test_render_md_lists_per_doc_metrics_and_worst_pages():
    pages = [
        {"doc": "a", "page": 1, "blocks": 4, "intact": 3, "broken": 1, "missing": 0,
         "label_lines": 2, "label_intact": 1},
        {"doc": "b", "page": 9, "blocks": 5, "intact": 1, "broken": 4, "missing": 0,
         "label_lines": 0, "label_intact": 0},
    ]
    md = corpus_qa.render_md(
        {"engine": "v3", "name": "corpus-qa", "date": "2026-08-22"},
        {"by_doc": corpus_qa.aggregate(pages), "worst": corpus_qa.worst_pages(pages), "pages": pages})
    assert "block_integrity" in md and "label_integrity" in md
    assert any(line.startswith("a ") and "0.750" in line for line in md.splitlines())
    assert "b p.9" in md  # worst page first


def test_worst_pages_are_ordered_by_broken_count():
    pages = [
        {"doc": "a", "page": 1, "blocks": 4, "intact": 4, "broken": 0, "missing": 0},
        {"doc": "b", "page": 9, "blocks": 5, "intact": 1, "broken": 4, "missing": 0},
        {"doc": "a", "page": 3, "blocks": 3, "intact": 1, "broken": 2, "missing": 0},
    ]
    worst = corpus_qa.worst_pages(pages, n=2)
    assert [(p["doc"], p["page"]) for p in worst] == [("b", 9), ("a", 3)]


GOBLIN = ["Goblin", "Small humanoid (goblinoid), neutral evil",
          "Armor Class 15 (leather armor, shield)", "Hit Points 7 (2d6)", "Speed 30 ft."]


def test_stacked_blocks_that_stay_consecutive_are_adjacent():
    r = corpus_qa.grade_page("\n".join(GOBLIN), stack(*GOBLIN))
    assert (r["adjacent_pairs"], r["adjacent_ok"]) == (3, 3)  # "Goblin" is too short to key on


def test_stat_line_displaced_to_another_creature_breaks_adjacency():
    # The shipped v3 layout on SRD 5.1 p315: the goblin's AC line is intact but
    # glued onto the gnoll's Spear action, and its neighbours are gone.
    shipped = ("used with two hands to make a melee attack. Armor Class 15 (leather armor, shield)\n"
               "Longbow. Ranged Weapon Attack: +3 to hit\n\n"
               "Goblin\nSmall humanoid (goblinoid), neutral evil\n\nHit Points 7 (2d6)\nSpeed 30 ft.")
    r = corpus_qa.grade_page(shipped, stack(*GOBLIN))
    assert r["label_intact"] == 3                      # tearing alone cannot see this
    assert (r["adjacent_pairs"], r["adjacent_ok"]) == (3, 1)


def test_missing_neighbour_is_recall_not_displacement():
    # A page (or block) the engine dropped entirely must not read as displaced.
    r = corpus_qa.grade_page("Small humanoid (goblinoid), neutral evil\nSpeed 30 ft.", stack(*GOBLIN))
    assert (r["adjacent_pairs"], r["adjacent_ok"]) == (0, 0)
    r = corpus_qa.grade_page("", stack(*GOBLIN))
    assert r["adjacent_pairs"] == 0


def test_blocks_in_different_columns_are_never_a_pair():
    left = corpus_qa.NativeBlock(LEFT, 58, 100, 280, 160)
    right = corpus_qa.NativeBlock(RIGHT, 330, 100, 554, 160)
    r = corpus_qa.grade_page(f"{LEFT}\n\n{RIGHT}", [left, right])
    assert r["adjacent_pairs"] == 0


def test_page_emitted_empty_is_flagged():
    # Layout detected only the footer on a spell-table page → every span dropped.
    r = corpus_qa.grade_page("", stack(LEFT, RIGHT))
    assert r["empty"] is True and r["native_chars"] > 200 and r["engine_chars"] == 0
    assert corpus_qa.grade_page(f"{LEFT}\n{RIGHT}", stack(LEFT, RIGHT))["empty"] is False


def test_empty_pages_are_counted_and_listed_apart_from_worst():
    # 33 blank pages must not crowd the interleave list out of the report.
    pages = [
        {"doc": "a", "page": 1, "blocks": 4, "intact": 1, "broken": 3, "missing": 0, "empty": False},
        {"doc": "a", "page": 2, "blocks": 0, "intact": 0, "broken": 0, "missing": 0, "empty": True,
         "native_chars": 900, "engine_chars": 0},
    ]
    assert corpus_qa.aggregate(pages)["a"]["pages_empty"] == 1
    assert [(p["doc"], p["page"]) for p in corpus_qa.empty_pages(pages)] == [("a", 2)]
    assert [(p["doc"], p["page"]) for p in corpus_qa.worst_pages(pages)] == [("a", 1)]
    md = corpus_qa.render_md({"engine": "v3", "name": "x", "date": "d"},
                             {"by_doc": corpus_qa.aggregate(pages), "worst": corpus_qa.worst_pages(pages),
                              "empty": corpus_qa.empty_pages(pages), "pages": pages})
    assert "## Empty pages (1)" in md and "a p.2" in md

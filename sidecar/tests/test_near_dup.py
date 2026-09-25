"""Cross-edition near-dup collapse (roadmap 2.3)."""
from legend_lore.near_dup import collapse_near_dups, leaf_title


def test_leaf_title_normalises():
    assert leaf_title("Monsters A–Z > **Goblin Warrior**") == "goblin warrior"


def _r(fn, heading, matched):
    return {"filename": fn, "source": f"/l/{fn}", "section_heading": heading, "matched_text": matched,
            "page_start": 1, "page_end": 1, "page_label_start": "", "page_label_end": "", "section_id": "s_" + fn}


def test_collapses_a_cross_edition_twin_into_also_in():
    a = _r("SRD_5.1.pdf", "Spells > Magic Missile", "You create three glowing darts of magical force. Each dart hits a creature of your choice.")
    b = _r("SRD_5.2.1.pdf", "Spells > Magic Missile", "You create three glowing darts of magical force. Each dart hits a creature of your choice.")
    out = collapse_near_dups([a, b])
    assert len(out) == 1 and out[0]["also_in"][0]["filename"] == "SRD_5.2.1.pdf"


def test_same_title_different_text_is_kept():
    a = _r("SRD_5.1.pdf", "Monsters > Goblin", "Small humanoid AC 15 HP 7 scimitar")
    b = _r("OSRIC.pdf", "Monsters > Goblin", "Frequency uncommon No. encountered 40-400 Move 60ft AC 6")
    assert len(collapse_near_dups([a, b])) == 2


def test_same_file_is_never_collapsed():
    a = _r("X.pdf", "A > T", "same text here"); b = _r("X.pdf", "B > T", "same text here")
    assert len(collapse_near_dups([a, b])) == 2


def test_empty_leaf_title_never_collapses():
    """"" == "" is not "same leaf_title" — two un-headed results from
    different files must never collapse on text similarity alone, even
    when near-identical (a normal pipeline output, not an edge case)."""
    a = _r("A.pdf", "", "The quick brown fox jumps over the lazy dog today")
    b = _r("B.pdf", "", "The quick brown fox jumps over the lazy dog tomorrow")
    assert len(collapse_near_dups([a, b])) == 2

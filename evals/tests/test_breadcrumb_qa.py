"""Breadcrumb QA: the heading string that feeds the embedding and the reranker
(roadmap 2026-09-02 §1.5 / Phase 0.2). Pure; no corpus."""
from evals.retrieval import breadcrumb_qa as bq


def test_markup_is_detected_and_stripped():
    h = "**Casting Spells** > **<u>Magic Missile</u>**"
    assert "markup" in bq.flaws(h)
    assert bq.strip_markup(h) == "Casting Spells > Magic Missile"


def test_stranded_letter_is_a_split_word_but_a_and_I_are_not():
    assert "split_letter" in bq.flaws("**S eed** **<u>p</u>** > **Goblin**")
    assert "split_letter" in bq.flaws("Dexterit y > Grappling")
    assert "split_letter" not in bq.flaws("A Pit > I Rolled")


def test_small_caps_mixed_case_is_flagged():
    assert "mixed_case" in bq.flaws("chaRacteR RaceS > Elves")
    assert "mixed_case" not in bq.flaws("Character Races > Elves")
    assert "mixed_case" not in bq.flaws("THAC0 > Combat")


def test_furniture_root_is_flagged():
    assert "furniture_root" in bq.flaws("**fOR fRee UpdateS, eRRata and OtheR OSRIc SUppORt, VISIt:** > Falling")
    assert "furniture_root" in bq.flaws("CONTENTS > FALLING")
    assert "furniture_root" not in bq.flaws("Combat > Falling")


def test_missing_heading_is_its_own_flaw():
    assert bq.flaws(None) == {"no_heading"}
    assert bq.flaws("") == {"no_heading"}


def test_grade_doc_counts_and_top_roots():
    chunks = [
        {"section_heading": "**fOR fRee UpdateS** > A", "chunk_type": "prose", "page_start": 1, "page_end": 1, "chars": 100},
        {"section_heading": "**fOR fRee UpdateS** > B", "chunk_type": "prose", "page_start": 2, "page_end": 2, "chars": 100},
        {"section_heading": "Combat > Falling", "chunk_type": "prose", "page_start": 3, "page_end": 3, "chars": 100},
        {"section_heading": None, "chunk_type": "table", "page_start": 4, "page_end": 4, "chars": 100},
    ]
    g = bq.grade_doc("osric_2e", chunks)
    assert g["chunks"] == 4
    assert g["markup"] == 2 and g["furniture_root"] == 2 and g["no_heading"] == 1
    assert g["top_roots"][0] == ("fOR fRee UpdateS", 2)


def test_aggregate_rates_and_all_bucket():
    rows = [bq.grade_doc("a", [{"section_heading": "**X** > Y", "chunk_type": "prose",
                                "page_start": 1, "page_end": 1, "chars": 10}]),
            bq.grade_doc("b", [{"section_heading": "X > Y", "chunk_type": "prose",
                                "page_start": 1, "page_end": 1, "chars": 10}])]
    s = bq.aggregate(rows)
    assert s["a"]["markup_rate"] == 1.0 and s["b"]["markup_rate"] == 0.0
    assert s["all"]["chunks"] == 2 and s["all"]["markup_rate"] == 0.5
    assert "markup_rate" in bq.format_report(s)


from evals.retrieval.breadcrumb_qa import flaws, regressions, residue


def test_markup_catches_single_star_underscore_and_hash():
    assert "markup" in flaws("*sEllinG EquipMEnt** > **Vex**")
    assert "markup" in flaws("_Gargantuan_ > Kraken")
    assert "markup" in flaws("# Combat > Grappling")
    assert "markup" not in flaws("Snake_eyes Tavern > Bar")   # underscore inside a word


def test_residue_lists_the_most_frequent_flawed_headings():
    chunks = [{"section_heading": "**S eed** **<u>p</u>** > **Goblin**"}] * 3 \
        + [{"section_heading": "chaRacteR RaceS > Elves"}] * 2 \
        + [{"section_heading": "Combat > Grappling"}]
    r = residue("srd", chunks, per_flaw=5)
    assert r["markup"][0] == ("**S eed** **<u>p</u>** > **Goblin**", 3)
    assert r["split_letter"][0][1] == 3
    assert r["mixed_case"] == [("chaRacteR RaceS > Elves", 2)]
    assert r["furniture_root"] == []


def test_regressions_flag_a_rate_that_rose_on_any_doc():
    ref = {"osric_2e": {"markup_rate": 0.0, "split_letter_rate": 0.0},
           "all": {"markup_rate": 0.0, "split_letter_rate": 0.0}}
    cur = {"osric_2e": {"markup_rate": 0.0, "split_letter_rate": 0.02},
           "all": {"markup_rate": 0.0, "split_letter_rate": 0.001}}
    regs = regressions(cur, ref)
    assert {(r["doc"], r["flaw"]) for r in regs} == {("osric_2e", "split_letter"), ("all", "split_letter")}


def test_regressions_ignore_docs_missing_on_either_side():
    assert regressions({"a": {"markup_rate": 0.5}}, {"b": {"markup_rate": 0.0}}) == []


def test_split_letter_ignores_letters_joined_by_dashes_apostrophes_or_die_percent():
    for h in ("Monsters A–Z > Young Gold Dragon", "Appendix MM-B: Nonplayer Characters > Priest",
              "Monsters > Will-­‐o’-­‐Wisp", "LEARNING MAGIC > NATURE’S CURE",
              "Jewellery Table > roll d% and d10", "Rules > Player's Guide"):
        assert "split_letter" not in flaws(h), h


def test_split_letter_still_flags_real_stranded_letters():
    for h in ("S eed p > Goblin", "Dexterit y > Grappling", "Le endar Actions g y", "Ran er S ells g p"):
        assert "split_letter" in flaws(h), h

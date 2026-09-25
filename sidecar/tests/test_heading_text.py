from legend_lore.heading_text import normalize_small_caps, repair_from_spans, sanitize, strip_markup


def _sp(text, size, bold=True):
    return {"text": text, "size": size, "bold": bold}


def test_strip_markup_removes_emphasis_tags_and_hash():
    assert strip_markup("**Monsters A–Z** > **<mark>Medusa</mark>** > <u>Actions</u>") \
        == "Monsters A–Z > Medusa > Actions"
    assert strip_markup("*sEllinG EquipMEnt**") == "sEllinG EquipMEnt"
    assert strip_markup("_Gargantuan_ **_,_** chaotic") == "Gargantuan , chaotic"
    assert strip_markup("# Combat<br>Grappling") == "Combat Grappling"
    assert strip_markup('Combat<br class="x">Grappling') == "Combat Grappling"
    assert strip_markup("Snake_eyes Tavern") == "Snake_eyes Tavern"
    assert strip_markup("  Two   spaces ") == "Two spaces"
    assert strip_markup("<Character Name> > Sheet") == "<Character Name> > Sheet"
    assert strip_markup("<MARK>Medusa</MARK>") == "Medusa"


def test_normalize_small_caps_title_cases_only_mixed_words():
    assert normalize_small_caps("chaRacteR RaceS") == "Character Races"
    assert normalize_small_caps("sEllinG EquipMEnt") == "Selling Equipment"
    assert normalize_small_caps("mUltI-claSSInG and dUal-claSSInG") == "Multi-classing and Dual-classing"
    assert normalize_small_caps("THAC0 and PCs at d20") == "THAC0 and PCs at d20"
    assert normalize_small_caps("Speed") == "Speed"


def test_repair_rejoins_a_descender_from_the_page_spans():
    spans = [_sp("Kraken", 13.9), _sp("Speed ", 9.8, bold=True), _sp("30 ft.", 9.8, bold=False)]
    assert repair_from_spans("S eed p", spans) == [("Speed", (9.8, True))]


def test_repair_splits_a_merged_pair_of_headings_by_font():
    spans = [_sp("Elf Traits ", 13.9), _sp("Halfling ", 18.0), _sp("Halfling Traits ", 13.9),
             _sp("Your halfling character", 9.8, bold=False)]
    assert repair_from_spans("Halfling Halflin Traits g", spans) == \
        [("Halfling", (18.0, True)), ("Halfling Traits", (13.9, True))]


def test_repair_joins_same_font_spans_into_one_heading():
    spans = [_sp("Ranger ", 18.0), _sp("Spells ", 18.0)]
    assert repair_from_spans("Ran er S ells g p", spans) == [("Ranger Spells", (18.0, True))]


def test_repair_requires_fragment_order_not_just_an_anagram():
    # "dear" is an anagram of "read"+"" but the fragments are out of order.
    spans = [_sp("dear", 12.0)]
    assert repair_from_spans("rea d", spans) == [("rea d", None)]


def test_repair_leaves_a_clean_heading_alone():
    assert repair_from_spans("Combat", [_sp("Combat", 12.0)]) == [("Combat", None)]
    assert repair_from_spans("A Pit and I", [_sp("A Pit and I", 12.0)]) == [("A Pit and I", None)]


def test_repair_ignores_spans_below_min_size():
    spans = [_sp("Speed", 9.8, bold=False)]
    assert repair_from_spans("S eed p", spans, min_size=12.0) == [("S eed p", None)]


def test_repair_ignores_letters_joined_by_dashes_or_apostrophes():
    assert repair_from_spans("Monsters A–Z", [_sp("Monsters A-Z", 18.0)]) == [("Monsters A–Z", None)]
    assert repair_from_spans("NATURE’S CURE", [_sp("NATURE'S CURE", 12.0)]) == [("NATURE’S CURE", None)]
    # a real stranded letter must still repair
    spans = [_sp("Kraken", 13.9), _sp("Speed ", 9.8, bold=True), _sp("30 ft.", 9.8, bold=False)]
    assert repair_from_spans("S eed p", spans) == [("Speed", (9.8, True))]


def test_sanitize_chains_the_three_rules():
    spans = [_sp("Ranger ", 18.0), _sp("Spells ", 18.0)]
    assert sanitize("**Ran er S ells** **<u>g p</u>**", spans) == [("Ranger Spells", (18.0, True))]
    assert sanitize("**chaRacteR RaceS**", []) == [("Character Races", None)]
    assert sanitize("****", []) == []

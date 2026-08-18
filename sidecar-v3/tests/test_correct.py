"""Phase 3 rung 7 — library-vocab spell correction (plan §3.4). Norvig-style
edit-distance to known terms; no error enumeration. Pure over a freq callable."""
from query.correct import correct

FREQ = {"fireball": 10, "bugbear": 5, "shillelagh": 3, "armor": 20, "goblin": 8, "damage": 30}
def freq(t):
    return FREQ.get(t, 0)


def test_corrects_typo_to_nearest_vocab_term():
    assert correct("fireabll damage", freq) == "fireball damage"  # transpose → known term


def test_corrects_domain_term_typo():
    assert correct("shillelag", freq) == "shillelagh"  # edit-1 insert; domain term a stock checker'd mangle


def test_edit_distance_two():
    assert correct("bugbayr", freq) == "bugbear"  # two edits from a known term


def test_known_term_unchanged():
    assert correct("fireball goblin armor", freq) == "fireball goblin armor"


def test_short_tokens_not_corrected():
    assert correct("ac hp 1d6", freq) == "ac hp 1d6"  # <4 chars → left alone (too ambiguous)


def test_unknown_uncorrectable_kept():
    assert correct("xyzzy plugh", freq) == "xyzzy plugh"  # no near vocab term → unchanged


def test_case_preserved_for_unchanged_token():
    assert correct("Fireball", freq) == "Fireball"  # known → original case kept

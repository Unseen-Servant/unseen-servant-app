"""Unit tests for spelling.py — library-derived vocabulary + spell correction.

Covers the spec's unit surface (docs/retrieval/2026-07-10-typo-
tolerance-design.md): vocabulary build (frequencies, junk-term
thresholding), OOV detection, correction rules (typos corrected; proper
nouns, digit tokens, short tokens, and non-ASCII untouched), query-span
reconstruction, and section B split/join variant generation.
"""

import pytest

from legend_lore.granularity import EmbedUnit
from legend_lore.spelling import (
    MIN_VOCAB_FREQ, SpellCorrector, build_vocabulary_from_store,
    trailing_token,
)
from tests.conftest import TEST_EMBED_DIM, seed_book


def _index(store, *rows):
    """Index (text, section_heading) rows as one book."""
    units = [
        EmbedUnit(
            chunk_id=f"c{i}", text=text, parent_id=f"p{i}", chunk_type="prose",
            section_heading=heading, source_pdf="/lib/x.pdf",
            page_start=1, page_end=1, ordinal=i,
        )
        for i, (text, heading) in enumerate(rows)
    ]
    seed_book(
        store, lambda texts: [[1.0] + [0.0] * (TEST_EMBED_DIM - 1)] * len(texts),
        "/lib/x.pdf", units,
    )


# ---------------------------------------------------------------------------
# Vocabulary build
# ---------------------------------------------------------------------------

def test_build_vocabulary_counts_lowercased_frequencies(test_store):
    _index(test_store, ("Chain mail armor", None), ("chain MAIL", None))
    vocab = build_vocabulary_from_store(test_store)
    assert vocab["chain"] == 2
    assert vocab["mail"] == 2
    assert vocab["armor"] == 1


def test_build_vocabulary_includes_section_heading_terms(test_store):
    _index(test_store, ("AC 22, HD 11", "Cloud Dragon"))
    vocab = build_vocabulary_from_store(test_store)
    assert vocab["cloud"] == 1
    assert vocab["dragon"] == 1


# ---------------------------------------------------------------------------
# Correction
# ---------------------------------------------------------------------------

VOCAB = {
    "armor": 60, "class": 60, "bonus": 20, "and": 100, "weight": 20,
    "for": 100, "chain": 50, "mail": 40, "dragon": 30, "cloud": 20,
    "appears": 10, "stats": 10, "damage": 80, "the": 100, "of": 100,
    "tiamat": 5,
    # junk under MIN_VOCAB_FREQ: neither protected nor a correction target
    "dragonx": 2,
}


@pytest.fixture
def corrector():
    return SpellCorrector(VOCAB)


def test_clean_query_is_a_strict_noop(corrector):
    assert corrector.correct("Armor class bonus and weight for chain mail") is None


def test_deletion_typo_corrected(corrector):
    assert corrector.correct("dragn stats") == "dragon stats"


def test_transposition_typo_corrected(corrector):
    assert corrector.correct("dargon stats") == "dragon stats"


def test_corrected_token_keeps_query_casing(corrector):
    assert corrector.correct("Cloud Dragn appears") == "Cloud Dragon appears"


def test_reconstruction_preserves_punctuation_and_other_tokens(corrector):
    assert (
        corrector.correct("Armor class: dragn MAIL!")
        == "Armor class: dragon MAIL!"
    )


def test_in_vocab_token_never_rewritten(corrector):
    # "tiamat" is rare (freq 5) but in-vocab — proper nouns stay.
    assert corrector.correct("tiamat stats") is None


def test_junk_vocab_term_is_not_a_correction_target(corrector):
    # "dragonxx" is distance 1 from junk "dragonx" (freq 2 < MIN_VOCAB_FREQ)
    # and distance 2 from "dragon" — the junk term must not win.
    assert corrector.correct("dragonxx stats") == "dragon stats"


def test_junk_vocab_term_is_itself_correctable(corrector):
    # freq < MIN_VOCAB_FREQ does not protect a token from correction.
    assert corrector.correct("dragonx stats") == "dragon stats"


def test_digit_tokens_untouched(corrector):
    assert corrector.correct("1d6 damage for d20 5e") is None


def test_short_tokens_untouched(corrector):
    # len <= 2 tokens are never corrected, even when OOV.
    assert corrector.correct("ac of xy chain") is None


def test_non_ascii_query_untouched(corrector):
    # Non-ASCII queries skip correction entirely (the ASCII token regex
    # would otherwise see fragments like "caf" for "café"), consistent
    # with _rerank_safe_for_query.
    assert corrector.correct("dégâts chan mail") is None


def test_edit_distance_capped_at_1_for_short_tokens(corrector):
    # len <= 4: max edit distance 1. "chab" is distance 2 from "chain".
    assert corrector.correct("chab damage") is None
    # ...but distance 1 still corrects: "mal" -> "mail".
    assert corrector.correct("mal damage") == "mail damage"


def test_edit_distance_2_for_longer_tokens(corrector):
    # "draggin" is distance 2 from "dragon" and long enough to allow it.
    assert corrector.correct("draggin stats") == "dragon stats"


def test_oov_with_no_near_match_stays(corrector):
    assert corrector.correct("xyzzt stats") is None


def test_english_word_missing_from_library_is_protected(corrector):
    # "classes" is real English the library may simply never print
    # (2026-07-10 eval: "stats" -> "starts", "Black Flag" -> "Black
    # Flat"). Words in the general-English list are never rewritten,
    # even with a near library term ("class").
    assert corrector.correct("classes of armor") is None


def test_english_protection_wins_over_plausible_typo(corrector):
    # The trade-off, pinned: "chan" reads as a "chain" typo but is in
    # the English list (proper name), so it stays.
    assert corrector.correct("chan mail") is None


def test_min_vocab_freq_constant():
    assert MIN_VOCAB_FREQ == 3


# ---------------------------------------------------------------------------
# Variant expansion (section B: split/join)
# ---------------------------------------------------------------------------

EXPANSION_VOCAB = {
    "owl": 10, "bear": 20, "owlbear": 8,
    "chain": 50, "mail": 40, "chainmail": 12,
    "cloud": 20, "dragon": 30,
    "fire": 40, "ball": 15, "fireball": 25,
    "armor": 60, "class": 60, "damage": 80, "challenge": 10,
    "rating": 10, "of": 100, "an": 100, "and": 100, "the": 100,
    "s": 200, "word": 30, "sword": 15,
    # junk under MIN_VOCAB_FREQ
    "spellslots": 2, "slots": 2,
}


@pytest.fixture
def expander():
    return SpellCorrector(EXPANSION_VOCAB)


def test_join_variant_when_concatenation_in_vocab(expander):
    assert expander.expand("challenge rating of an owl bear") == [
        "challenge rating of an owlbear"
    ]


def test_split_variant_when_both_parts_in_vocab(expander):
    # "clouddragon" is OOV but splits into two in-vocab parts.
    assert expander.expand("clouddragon armor class") == [
        "cloud dragon armor class"
    ]


def test_split_applies_to_in_vocab_token_too(expander):
    # "chainmail" is itself in-vocab (freq 12) — the split variant is
    # still generated (the design: token t, in-vocab or not).
    assert expander.expand("chainmail damage") == ["chain mail damage"]


def test_split_boundary_maximizes_min_part_freq():
    # "dragonfire" = dragon+fire (min 30) or drag+onfire (min 3):
    # the boundary with the higher min-frequency wins.
    vocab = {"dragon": 30, "fire": 40, "drag": 100, "onfire": 3}
    assert SpellCorrector(vocab).expand("dragonfire") == ["dragon fire"]


def test_one_edit_per_variant(expander):
    # A join spot and a split spot yield two variants, each applying
    # exactly one edit; scan order (left to right) is preserved.
    assert expander.expand("owl bear chainmail") == [
        "owlbear chainmail",
        "owl bear chain mail",
    ]


def test_at_most_two_variants(expander):
    assert (
        expander.expand("owl bear chainmail fireball") == [
            "owlbear chainmail fireball",
            "owl bear chain mail fireball",
        ]
    )


def test_no_variants_for_plain_query(expander):
    assert expander.expand("armor class and damage") == []


def test_join_requires_in_vocab_concatenation(expander):
    # "armorclass" is not a corpus term — adjacency alone never joins.
    assert expander.expand("armor class") == []


def test_junk_frequency_blocks_join_and_split(expander):
    # "spellslots"/"slots" sit under MIN_VOCAB_FREQ: "spell slots" must
    # not join, and "spellslots" must not split into a junk part.
    vocab = {**EXPANSION_VOCAB, "spell": 30}
    expander = SpellCorrector(vocab)
    assert expander.expand("spell slots") == []
    assert expander.expand("spellslots") == []


def test_split_parts_must_be_at_least_three_chars(expander):
    # "sword" = s+word with both "parts" frequent in the vocab ("s" from
    # possessive tokenization) — single/double-letter parts are
    # artifacts, never split evidence.
    assert expander.expand("sword damage") == []


def test_join_only_across_pure_whitespace(expander):
    # Punctuation between the tokens means they are not one term.
    assert expander.expand("owl, bear") == []


def test_join_preserves_casing_and_surroundings(expander):
    assert expander.expand("Fire ball damage!") == ["Fireball damage!"]


def test_split_preserves_casing_and_surroundings(expander):
    assert expander.expand("the Clouddragon's lair") == [
        "the Cloud dragon's lair"
    ]


def test_non_ascii_query_has_no_variants(expander):
    assert expander.expand("dégâts chainmail") == []


# ---------------------------------------------------------------------------
# Context tie-break (roadmap 3.5)
# ---------------------------------------------------------------------------

# "thif" is one edit from both; raw frequency alone picks "this".
TIE_VOCAB = {"this": 5000, "thief": 400, "skill": 300, "how": 900,
             "does": 400, "dies": 800, "grappling": 50, "dnd": 0}


def _counter(table):
    return lambda phrases: {p: table.get(p, 0) for p in phrases}


def test_frequency_decides_a_tie_without_context():
    sc = SpellCorrector(TIE_VOCAB)
    assert sc.correct("thif") == "this"


def test_library_phrase_context_breaks_the_tie():
    """The library prints "thief skill" far more than "this skill"."""
    sc = SpellCorrector(
        TIE_VOCAB, phrase_counts=_counter({("thief", "skill"): 95, ("this", "skill"): 6}))
    assert sc.correct("thif skill") == "thief skill"


def test_english_bigrams_settle_the_question_frame():
    """Rulebooks never print "how does"; English bigrams know it beats
    "how dies", which is more frequent in the library."""
    sc = SpellCorrector(TIE_VOCAB, phrase_counts=_counter({}))
    assert sc.correct("how dpes grappling") == "how does grappling"


def test_protected_tokens_are_never_rewritten():
    """System keywords ("dnd") are boost cues the library may never print."""
    sc = SpellCorrector({"and": 5000, "grappling": 50})
    assert sc.correct("dnd grappling") == "and grappling"
    assert sc.correct("dnd grappling", protected={"dnd"}) is None


def test_keyword_tokens_splits_multiword_keywords():
    from legend_lore.spelling import keyword_tokens

    assert keyword_tokens({"D&D 5E": ["dnd", "d&d"], "YZE": ["Year Zero"]}) >= {
        "dnd", "d", "year", "zero"}


# ---------------------------------------------------------------------------
# Completion of a still-being-typed last word (partial searches)
# ---------------------------------------------------------------------------


def test_trailing_token_is_the_last_word_lowercased():
    assert trailing_token("Goblin Armor CLA") == "cla"
    assert trailing_token("chain mail?") == "mail"
    assert trailing_token("???") == ""


def test_complete_finishes_the_last_word_with_the_most_frequent_match(corrector):
    assert corrector.complete("chain mail armor cla") == "chain mail armor class"
    assert corrector.complete("fire dam") == "fire damage"


def test_complete_only_touches_the_last_word(corrector):
    # "dam" mid-query is left alone; only the word being typed completes.
    assert corrector.complete("dam of dra") == "dam of dragon"


def test_complete_never_offers_junk_under_the_vocabulary_threshold(corrector):
    # "dragonx" (freq 2) is below MIN_VOCAB_FREQ, so "dragon" wins even
    # though "dragonx" also starts with the prefix.
    assert corrector.complete("the dragon") is None
    assert corrector.complete("the drag") == "the dragon"


def test_complete_leaves_short_digit_and_unknown_prefixes(corrector):
    assert corrector.complete("armor cl") is None      # under 3 letters
    assert corrector.complete("level 5e") is None      # digits
    assert corrector.complete("owlbe") is None         # no vocabulary match
    assert corrector.complete("") is None


def test_complete_keeps_the_capital_of_the_typed_word(corrector):
    assert corrector.complete("Chain Mai") == "Chain Mail"


def test_complete_uses_the_left_neighbour_as_context():
    vocab = {"points": 90, "poison": 40, "against": 50, "hit": 50}
    counts = _counter({("against", "poison"): 30, ("hit", "points"): 40})
    sc = SpellCorrector(vocab, phrase_counts=counts)
    assert sc.complete("save against poi") == "save against poison"
    assert sc.complete("hit poi") == "hit points"

